# ruff: noqa: E501
"""`GET /ui/pendientes/sueltos` (U13b) — cola de solo lectura sobre Postgres real.

La cola recorre SOLO los sueltos de A: no aplica, crea, mueve, ignora ni persiste nada. La
candidata se lee de `metadata.candidates`, nunca de `tradition_guess`, y no se comprueba contra
`series`. Ningún fichero existe en disco. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import html as htmllib
import os
import re
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import BIB, Banco, archivo, candidatas
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import revision_carpetas
from zascarr.services.revision_carpetas import RevisionCarpetas, _candidata_guardada

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

RUTA = "/ui/pendientes/sueltos"
ACCIONES = re.compile(
    r"<form\b|<button\b|hx-(?:post|delete|put|patch)=|type=[\"']submit[\"']|>\s*Ignorar\s*<",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd, monkeypatch):
    b = Banco(url_bd)
    await b.limpiar()
    monkeypatch.setattr(revision_carpetas, "get_settings", lambda: SimpleNamespace(library_path=Path(BIB)))

    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    yield b
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


def cliente(**kw) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost",
        headers={"Origin": "http://localhost"}, **kw,
    )


async def pagina(params: dict | None = None, ruta: str = RUTA) -> httpx.Response:
    async with cliente() as c:
        return await c.get(ruta, params=params)


def principal(cuerpo: str) -> str:
    """Solo el contenido de la página (sin menú ni pie legal)."""
    return cuerpo.split("<main", 1)[1].split("<footer", 1)[0]


def visible(cuerpo: str) -> str:
    """El texto que lee la persona: sin etiquetas, con entidades resueltas y espacios normalizados."""
    sin_etiquetas = re.sub(r"<[^>]+>", " ", principal(cuerpo))
    return re.sub(r"\s+", " ", htmllib.unescape(sin_etiquetas)).strip()


def nombres_en(cuerpo: str) -> list[str]:
    return re.findall(r'class="filename suelto-nombre"[^>]*>([^<]+)</h2>', cuerpo)


def cursor(cuerpo: str, rel: str) -> str:
    encontrado = re.search(rf'<a rel="{rel}" href="([^"]+)">', cuerpo)
    assert encontrado, f"no hay enlace rel={rel}"
    return htmllib.unescape(encontrado.group(1))


# ── Universo y tarjetas ──────────────────────────────────────────────────────────────────────────

class TestColaDeSueltos:

    async def test_incluye_solo_sueltos_de_a_y_no_el_agrupado_ni_b(self, banco):
        await banco.sembrar(
            archivo("Comics/Suelto raíz.cbz"),
            archivo("Comics/_Omnibus/Suelto en contenedor.cbz"),
            archivo("Comics/Revisar/Suelto en revisar.cbz"),
            archivo("Comics/Una serie/Agrupado sin candidata.cbz"),
            archivo("Comics/Otro suelto de B.cbz", estado="direct",
                    cands=candidatas(uuid4(), "Candidata de B", 2001)),
        )
        r = await pagina()
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        t = visible(r.text)
        assert "Suelto raíz.cbz" in t
        assert "Suelto en contenedor.cbz" in t
        assert "Suelto en revisar.cbz" in t
        assert "Agrupado sin candidata.cbz" not in t
        assert "Otro suelto de B.cbz" not in t
        assert "Sueltos 1–3 de 3" in t
        assert "3 de 4 por revisar" in t
        assert ACCIONES.search(principal(r.text)) is None

    async def test_el_subtitulo_aclara_que_no_se_puede_ignorar_y_remite_a_por_revisar(self, banco):
        await banco.sembrar(archivo("Comics/_Omnibus/Suelto.cbz"))
        r = await pagina()
        assert r.status_code == 200
        t = visible(r.text)
        assert "Solo lectura: desde aquí no se asigna, crea, mueve ni ignora nada." in t
        assert "Para ignorar un pendiente, ábrelo en «Por revisar»." in t

    async def test_candidata_guardada_sin_tradicion_y_sin_comprobar_la_serie(self, banco):
        con_tradicion = archivo("Comics/_Omnibus/Con tradición 01.cbz",
                                cands=candidatas(uuid4(), "Serie con tradición", 1987, 0.94))
        con_tradicion.metadata_["tradition_guess"] = "BD"
        sin_tradicion = archivo("Comics/_Omnibus/Sin tradición 01.cbz",
                                cands=candidatas(uuid4(), "Serie sin tradición", None, 0.88))
        sin_candidata = archivo("Comics/_Omnibus/Sin candidata 01.cbz")
        sin_candidata.metadata_["tradition_guess"] = "Europea"
        ilegible = archivo("Comics/_Omnibus/Ilegible 01.cbz", cands=[{"title": "Falta serie y puntuación"}])
        borrada = archivo("Comics/_Omnibus/Borrada 01.cbz",
                          cands=candidatas(uuid4(), "Serie que no está en la BD", 1999, 0.5))
        await banco.sembrar(con_tradicion, sin_tradicion, sin_candidata, ilegible, borrada)

        r = await pagina()
        assert r.status_code == 200
        t = visible(r.text)
        assert "«Serie con tradición» (1987)" in t and "94% · no aplicada" in t
        assert "«Serie sin tradición»" in t and "88% · no aplicada" in t
        assert "Sin serie candidata guardada" in t
        assert "Sin candidata 01.cbz" in t
        assert "No se pudo leer la sugerencia guardada" in t
        assert "«Serie que no está en la BD»" in t and "ya no existe" not in t
        assert t.count("Sugerencia guardada:") == 3
        assert ACCIONES.search(principal(r.text)) is None

    async def test_candidatas_mal_formadas_no_tumban_la_cola(self, banco):
        await banco.sembrar(
            archivo("Comics/_Omnibus/Año no convertible.cbz", cands=[{
                "series_id": str(uuid4()), "title": "Serie", "score": 0.9, "start_year": "²",
            }]),
            archivo("Comics/_Omnibus/Serie no textual.cbz", cands=[{
                "series_id": 123, "title": "Serie", "score": 0.9,
            }]),
            archivo("Comics/_Omnibus/Título no textual.cbz", cands=[{
                "series_id": str(uuid4()), "title": {"x": 1}, "score": 0.9,
            }]),
            archivo("Comics/_Omnibus/Puntuación booleana.cbz", cands=[{
                "series_id": str(uuid4()), "title": "Serie", "score": True,
            }]),
        )

        r = await pagina()
        assert r.status_code == 200
        t = visible(r.text)
        assert t.count("No se pudo leer la sugerencia guardada") == 4
        assert "No se pudieron leer los archivos sueltos" not in t
        assert "Sugerencia guardada:" not in t

    async def test_el_nombre_largo_se_lee_entero_y_la_tarjeta_tiene_nombre_accesible(self, banco):
        largo = "Un nombre de archivo extraordinariamente largo que no cabe en una línea estrecha y debe partirse sin recortarse (1987).cbz"
        await banco.sembrar(archivo(f"Comics/_Omnibus/{largo}"))
        r = await pagina()
        assert largo in visible(r.text)
        assert re.search(r'aria-labelledby="suelto-[0-9a-f-]+"', r.text)
        assert re.search(r'<h2 class="filename suelto-nombre" id="suelto-[0-9a-f-]+">', r.text)
        assert '<nav class="pend-paginas' not in principal(r.text)  # una sola página: sin paginación

    async def test_la_vista_individual_enlaza_a_la_cola(self, banco):
        await banco.sembrar(archivo("Comics/_Omnibus/Suelto.cbz"))
        r = await pagina(ruta="/ui/pendientes")
        assert r.status_code == 200
        assert 'href="/ui/pendientes/sueltos"' in principal(r.text)
        assert "Ver los archivos sueltos" in visible(r.text)

    async def test_sin_sueltos_el_vacio_no_se_confunde_con_error(self, banco):
        await banco.sembrar(archivo("Comics/Una serie/Agrupado.cbz"))
        r = await pagina()
        assert r.status_code == 200
        t = visible(r.text)
        assert "No hay archivos sueltos." in t
        assert "No se pudieron leer" not in t
        assert "Volver a las carpetas" in t
        assert "Sueltos 0" not in t
        assert r.headers["cache-control"] == "no-store"


class TestCandidataGuardadaMalFormada:
    """Una candidata rota se degrada a ilegible; nunca debe propagar una excepción."""

    @pytest.mark.parametrize(
        "candidata",
        [
            pytest.param(
                {"series_id": str(uuid4()), "title": "Serie", "score": 0.9, "start_year": "²"},
                id="start-year-no-convertible",
            ),
            pytest.param(
                {"series_id": 123, "title": "Serie", "score": 0.9},
                id="series-id-no-textual",
            ),
            pytest.param(
                {"series_id": str(uuid4()), "title": {"x": 1}, "score": 0.9},
                id="title-no-textual",
            ),
            pytest.param(
                {"series_id": str(uuid4()), "title": "Serie", "score": True},
                id="score-booleano",
            ),
        ],
    )
    def test_devuelve_ilegible(self, candidata):
        assert _candidata_guardada({"candidates": [candidata]}) == (None, True)


# ── Cursor y ausencia de OFFSET ──────────────────────────────────────────────────────────────────

class TestCursor:

    async def test_pagina_50_con_anterior_y_siguiente_sin_saltos(self, banco):
        await banco.sembrar(*(archivo(f"Comics/_Omnibus/Suelto {i:02d}.cbz") for i in range(51)))

        primera = await pagina()
        assert primera.status_code == 200
        assert "Sueltos 1–50 de 51" in visible(primera.text)
        assert 'rel="prev"' not in primera.text
        siguiente = cursor(primera.text, "next")

        segunda = await pagina(ruta=siguiente)
        assert segunda.status_code == 200
        assert "Sueltos 51–51 de 51" in visible(segunda.text)
        assert 'rel="next"' not in segunda.text
        volver = cursor(segunda.text, "prev")

        tercera = await pagina(ruta=volver)
        assert "Sueltos 1–50 de 51" in visible(tercera.text)

        todos = nombres_en(primera.text) + nombres_en(segunda.text)
        assert len(todos) == 51 and len(set(todos)) == 51
        assert set(todos) == {f"Suelto {i:02d}.cbz" for i in range(51)}

    async def test_cursor_invalido_o_las_dos_claves_dan_la_primera_pagina(self, banco):
        await banco.sembrar(*(archivo(f"Comics/_Omnibus/Suelto {i:02d}.cbz") for i in range(51)))
        primera = await pagina()
        siguiente = cursor(primera.text, "next")
        clave = parse_qs(urlparse(siguiente).query)["despues"][0]

        invalido = await pagina(params={"despues": "no-es-una-clave"})
        assert "Sueltos 1–50 de 51" in visible(invalido.text)

        ambas = await pagina(params={"despues": clave, "antes": clave})
        assert "Sueltos 1–50 de 51" in visible(ambas.text)
        assert 'rel="prev"' not in ambas.text

    async def test_cursor_que_ya_no_existe_vuelve_a_la_primera_pagina(self, banco):
        await banco.sembrar(*(archivo(f"Comics/_Omnibus/Suelto {i:02d}.cbz") for i in range(51)))
        primera = await pagina()
        siguiente = cursor(primera.text, "next")
        ultimo_id = re.findall(r'id="suelto-([0-9a-f-]+)"', primera.text)[-1]
        ultimo_nombre = nombres_en(primera.text)[-1]

        async with banco.fabrica() as s:
            await s.execute(text("UPDATE files SET review_dismissed = true WHERE id = :id"), {"id": ultimo_id})
            await s.commit()

        recuperada = await pagina(ruta=siguiente)
        assert recuperada.status_code == 200
        assert "Sueltos 1–50 de 50" in visible(recuperada.text)
        assert ultimo_nombre not in visible(recuperada.text)  # el cursor ya no existe en A

    async def test_una_sola_consulta_select_y_sin_offset(self, banco):
        await banco.sembrar(*(archivo(f"Comics/_Omnibus/Suelto {i:02d}.cbz") for i in range(10)))
        async with banco.fabrica() as s:
            antes = (await s.execute(text(
                "SELECT id, review_dismissed, metadata FROM files ORDER BY id"))).all()
        banco.sentencias.clear()
        r = await pagina()
        assert r.status_code == 200
        consultas = [s for s in banco.sentencias if s.lstrip().upper().startswith(("SELECT", "WITH"))]
        assert len(consultas) == 1, banco.sentencias
        assert "OFFSET" not in consultas[0].upper()
        assert "FROM series" not in consultas[0].lower()
        assert not [s for s in banco.sentencias if not s.lstrip().upper().startswith(("SELECT", "WITH"))]
        async with banco.fabrica() as s:
            despues = (await s.execute(text(
                "SELECT id, review_dismissed, metadata FROM files ORDER BY id"))).all()
        assert antes == despues


# ── Fixture de referencia y medición local ───────────────────────────────────────────────────────

class TestReferenciaYPresupuesto:

    @staticmethod
    async def _sembrar_referencia(banco: Banco):
        archivos = []
        for i in range(108):
            repeticiones = 13 if i < 12 else 12
            archivos.extend(archivo(f"Comics/Carpeta {i:03d}/Cosa {j:02d}.cbz") for j in range(repeticiones))
        archivos.extend(archivo(f"Comics/_Omnibus/Suelto {j:02d}.cbz") for j in range(14))
        archivos.extend(
            archivo(f"Comics/Serie B {j:02d}/Sugerida {j:02d}.cbz", estado="direct",
                    cands=candidatas(uuid4(), f"Serie B {j:02d}", 2000 + j))
            for j in range(17)
        )
        await banco.sembrar(*archivos)

    async def test_referencia_1322_con_14_sueltos_y_17_b_fuera(self, banco):
        await self._sembrar_referencia(banco)
        r = await pagina()
        assert r.status_code == 200
        t = visible(r.text)
        assert "Sueltos 1–14 de 14" in t
        assert "14 de 1.322 por revisar" in t
        assert "Sugerida 00.cbz" not in t

    async def test_medicion_local_20_lecturas(self, banco):
        await self._sembrar_referencia(banco)
        tiempos = []
        for _ in range(20):
            inicio = time.perf_counter()
            r = await pagina()
            tiempos.append(time.perf_counter() - inicio)
            assert r.status_code == 200
        tiempos.sort()
        p95 = tiempos[int(len(tiempos) * 0.95) - 1] * 1000
        print(f"\nU13b local: 1.322 A / 14 sueltos; p95 HTML ASGI = {p95:.0f} ms")
        assert p95 < 1000, p95


# ── Fallo de lectura ────────────────────────────────────────────────────────────────────────────

class TestFallo:

    async def test_un_fallo_da_503_sin_recuentos_parciales(self, banco, monkeypatch):
        await banco.sembrar(archivo("Comics/_Omnibus/Suelto.cbz"))

        async def boom(*args, **kwargs):
            raise RuntimeError("la BD no responde")

        monkeypatch.setattr(RevisionCarpetas, "pagina_de_sueltos", boom)
        r = await pagina()
        assert r.status_code == 503
        assert r.headers["cache-control"] == "no-store"
        t = visible(r.text)
        assert "No se pudieron leer los archivos sueltos" in t
        assert "No se muestran recuentos parciales" in t
        assert "Sueltos 1" not in t and "de 1 por revisar" not in t
        assert "Reintentar" in t
