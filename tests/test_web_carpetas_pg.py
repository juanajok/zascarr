# ruff: noqa: E501
"""`GET /ui/pendientes/carpetas` (rebanada 1b) — la vista HTML de solo lectura, sobre Postgres real.

Reutiliza el servicio de 1a (`RevisionCarpetas`) y su respuesta; aquí se prueba lo que la vista añade o podría
estropear: el texto exacto que ve la persona, que el conflicto se vea y se explique, que se nombren los archivos
afectados, que lo del JSON y lo del HTML coincidan, la paginación, el escape de HTML, y que no haya ninguna
acción (ni formularios, ni botones, ni JS nuevo). Ningún fichero existe en disco. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import builtins
import html as htmllib
import os
import re
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import BIB, Banco, archivo, candidatas
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import revision_carpetas
from zascarr.services.revision_carpetas import (
    ETIQUETAS,
    ArchivoRevision,
    CarpetaLimpiaOut,
    Grupo,
    Pagina,
    PatronDeNombres,
    RespuestaCarpetas,
    Senal,
    Totales,
)

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

RUTA = "/ui/pendientes/carpetas"
FRASE = "registros pendientes de verificar, no archivos confirmados"
PALABRAS_PROHIBIDAS = re.compile(r"\b(reconocid\w*|clasificad\w*|lista)\b", re.IGNORECASE)
NOMBRES_SAGA = [
    f"Batman - Saga Scott Snyder {n:02d} - El Tribunal de los Buhos [SC][CRG].cbr" for n in range(1, 10)]


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
    """Solo el contenido de la página (`<main>` sin el pie legal): ni menú ni avisos legales."""
    dentro = cuerpo.split('<main', 1)[1].split('<footer', 1)[0]
    return dentro


def visible(cuerpo: str) -> str:
    """El texto que lee la persona: sin etiquetas, con entidades resueltas y espacios normalizados."""
    sin_etiquetas = re.sub(r"<[^>]+>", " ", principal(cuerpo))
    return re.sub(r"\s+", " ", htmllib.unescape(sin_etiquetas)).strip()


# ── Lo que ve la persona ──────────────────────────────────────────────────────────────────────────

class TestTextoYEtiquetas:

    async def test_la_frase_de_los_registros_pendientes_esta_siempre(self, banco):
        await banco.sembrar(archivo("Comics/A/Cosa 01.cbz"))
        r = await pagina()
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        assert FRASE in visible(r.text)
        assert r.headers["cache-control"] == "no-store"

    async def test_la_frase_sale_tambien_sin_nada_pendiente(self, banco):
        r = await pagina()
        assert FRASE in visible(r.text) and "Nada pendiente" in visible(r.text)

    async def test_las_catorce_filas_obsoletas_salen_como_sin_serie_sin_afirmar_que_existen(self, banco):
        f = archivo("Comics/Carpeta Antigua/Algo 01.cbz")
        f.is_missing = True
        await banco.sembrar(f)
        t = visible((await pagina()).text)
        assert "Comics/Carpeta Antigua" in t and "Sin serie" in t and FRASE in t
        assert "archivo confirmado" not in t.replace(FRASE, "")

    async def test_etiquetas_exactas_y_ninguna_palabra_que_prometa_de_mas(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            *(archivo(f"Comics/Batman - Saga de Scott Snyder (2019)/{n}", estado="direct",
                      cands=candidatas(sid, "BATMAN", 2025)) for n in NOMBRES_SAGA),
        )
        t = visible((await pagina()).text)
        for etiqueta in (ETIQUETAS["sin_serie"], ETIQUETAS["serie_sugerida"], "por confirmar", "en conflicto"):
            assert etiqueta in t, etiqueta
        sin_nombres = t
        for n in NOMBRES_SAGA:
            sin_nombres = sin_nombres.replace(n, "")
        assert PALABRAS_PROHIBIDAS.findall(sin_nombres) == []


class TestConflictoVisible:

    async def test_batman_saga_se_ve_en_conflicto_y_se_explica_con_los_nombres_afectados(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(*(
            archivo(f"Comics/Batman - Saga de Scott Snyder (2019)/{n}", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)) for n in NOMBRES_SAGA))
        t = visible((await pagina()).text)
        assert "Comics/Batman - Saga de Scott Snyder (2019)" in t
        assert "en conflicto" in t and "por confirmar" in t
        assert "La carpeta dice 2019; la serie sugerida empieza en 2025." in t
        assert "La carpeta añade «Saga de Scott Snyder»." in t
        assert "Afecta a 9 registros" in t
        assert "BATMAN (2025)" in t and "no está elegida ni asignada" in t
        for n in NOMBRES_SAGA:
            assert n in t                                   # los nombres afectados, a la vista

    async def test_un_archivo_minoritario_discrepante_se_nombra_y_los_demas_no(self, banco):
        sid = await banco.serie("Flash", 1987)
        await banco.sembrar(*(
            archivo(f"Comics/Flash/{n}", estado="direct", cands=candidatas(sid, "Flash", 1987))
            for n in ("Flash 01 (1987).cbz", "Flash 02 (1987).cbz", "Flash 03 (2011).cbz")))
        cuerpo = (await pagina()).text
        cuerpo = principal(cuerpo)
        assert "año que no cuadra" in cuerpo, "no se encontró la señal de año"
        desde = cuerpo.index("año que no cuadra")
        afectados = cuerpo[desde:].split("<details", 1)[1].split("</details>", 1)[0]
        assert "Flash 03 (2011).cbz" in afectados
        assert "Flash 01 (1987).cbz" not in afectados and "Flash 02 (1987).cbz" not in afectados

    async def test_un_grupo_que_corrobora_se_ve_sin_conflicto(self, banco):
        sid = await banco.serie("Absolute Batman", 2024)
        await banco.sembrar(*(
            archivo(f"Comics/Absolute Batman (2024)/Absolute Batman {n:02d}.cbz", estado="direct",
                    cands=candidatas(sid, "Absolute Batman", 2024)) for n in range(1, 4)))
        t = visible((await pagina()).text)
        assert "por confirmar" in t and "en conflicto" not in t
        assert "corroboran" in t

    async def test_grupo_mixto_distingue_los_dos_estados_de_cada_registro(self, banco):
        sid = await banco.serie("Absolute Batman", 2024)
        await banco.sembrar(
            archivo("Comics/Absolute Batman (2024)/Absolute Batman 01.cbz", estado="direct",
                    cands=candidatas(sid, "Absolute Batman", 2024)),
            archivo("Comics/Absolute Batman (2024)/Extra 01.cbz"),
        )
        cuerpo = (await pagina()).text
        t = visible(cuerpo)
        assert ETIQUETAS["mixto"] in t
        assert "Absolute Batman 01.cbz — Serie sugerida, falta confirmar número y edición" in t
        assert "Extra 01.cbz — Sin serie" in t

    async def test_candidatas_inexistentes_se_avisan_no_se_esconden(self, banco):
        from uuid import uuid4
        await banco.sembrar(archivo("Comics/R/Huerfana 01.cbz", estado="direct", cands=candidatas(uuid4(), "Borrada", 2000)))
        t = visible((await pagina()).text)
        assert "1 registros tenían una serie sugerida que ya no existe" in t


# ── La vista no recalcula nada ────────────────────────────────────────────────────────────────────

class TestSinLogicaPropia:

    async def test_el_html_muestra_lo_mismo_que_el_json(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            *(archivo(f"Comics/Batman - Saga de Scott Snyder (2019)/{n}", estado="direct",
                      cands=candidatas(sid, "BATMAN", 2025)) for n in NOMBRES_SAGA[:3]),
            archivo("Comics/Flash (1987)/Flash 01 (1987).cbz", estado="direct",
                    cands=candidatas(await banco.serie("Flash", 1987), "Flash", 1987)),
        )
        async with cliente() as c:
            datos = (await c.get("/api/revision/carpetas")).json()
            t = visible((await c.get(RUTA)).text)
        assert datos["grupos"]
        orden_html = [t.index(g["clave"]) for g in datos["grupos"]]
        assert orden_html == sorted(orden_html)                         # mismo orden
        for g in datos["grupos"]:
            assert g["etiqueta"] in t and str(g["n_archivos"]) in t
            for s in g["senales"]:
                assert s["texto"] in t, s["texto"]
            for a in g["archivos"]:
                assert a["nombre"] in t
        assert f"{datos['totales']['sin_serie']} sin serie" in t
        assert f"{datos['totales']['grupos']} carpetas" in t

    async def test_la_vista_pinta_lo_que_devuelve_el_servicio_sin_recalcular(self, banco, monkeypatch):
        """Una respuesta ENLATADA con un texto de señal inventado: si la vista lo recalculara, no saldría."""
        enlatada = RespuestaCarpetas(
            generado="2026-10-07T00:00:00Z",
            totales=Totales(sin_serie=0, serie_sugerida=1, grupos=1, candidata_inexistente=0),
            pagina=Pagina(limite=50, desplazamiento=0),
            grupos=[Grupo(
                clave="Comics/Inventada", carpeta_contextual="Inventada", ascendentes=["Comics"],
                carpeta_limpia=CarpetaLimpiaOut(titulo="Inventada", anio=None, volumen=None, calificadores=[]),
                estado="serie_sugerida", etiqueta=ETIQUETAS["serie_sugerida"], n_archivos=1,
                patron_de_nombres=PatronDeNombres(titulo_dominante="Inventada", proporcion=1.0, titulos_distintos=1),
                serie_sugerida=None, por_confirmar=True, en_conflicto=True,
                senales=[Senal(codigo="x", severidad="conflicto", texto="TEXTO-ENLATADO-DEL-SERVICIO", archivos=["id-1"])],
                archivos=[ArchivoRevision(id="id-1", nombre="Inventada 01.cbz", estado="serie_sugerida")],
            )],
        )

        async def falso(self, limite=200, desplazamiento=0):
            return enlatada
        monkeypatch.setattr(revision_carpetas.RevisionCarpetas, "carpetas", falso)
        t = visible((await pagina()).text)
        assert "TEXTO-ENLATADO-DEL-SERVICIO" in t and "Inventada 01.cbz" in t and "en conflicto" in t

    async def test_no_hay_ninguna_accion_ni_javascript_nuevo(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct", cands=candidatas(sid, "BATMAN", 2025)),
        )
        cuerpo = principal((await pagina()).text)
        for prohibido in ("<form", "<button", "<script", "hx-post", "hx-delete", "hx-put", "hx-get", "onclick", "onerror=", 'type="submit"'):
            assert prohibido not in cuerpo, prohibido
        plantilla = (Path(__file__).resolve().parents[1] / "src/zascarr/web/templates/carpetas.html").read_text(encoding="utf-8")
        assert "<script" not in plantilla and "hx-" not in plantilla


# ── Paginación, escape, solo lectura y acceso ────────────────────────────────────────────────────

class TestPaginacion:

    async def test_paginas_con_enlaces_correctos(self, banco):
        await banco.sembrar(*(archivo(f"Comics/G{i}/Cosa 01.cbz") for i in range(5)))
        primera = (await pagina({"limite": 2})).text
        assert "Carpetas 1–2 de 5" in visible(primera)
        assert 'rel="next"' in primera and "desplazamiento=2" in primera and 'rel="prev"' not in primera
        ultima = (await pagina({"limite": 2, "desplazamiento": 4})).text
        assert "Carpetas 5–5 de 5" in visible(ultima)
        assert 'rel="prev"' in ultima and "desplazamiento=2" in ultima and 'rel="next"' not in ultima

    async def test_una_sola_pagina_no_muestra_navegacion(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        assert "carpetas-paginas" not in (await pagina()).text

    async def test_la_muestra_limitada_se_dice(self, banco):
        await banco.sembrar(*(archivo(f"Comics/Larga/Cosa {i:03d}.cbz") for i in range(45)))
        t = visible((await pagina()).text)
        assert "Ver registros (20 de 45)" in t and "hay 25 más" in t

    @pytest.mark.parametrize("params", [{"limite": 0}, {"limite": 1001}, {"desplazamiento": -1}, {"limite": "x"}])
    async def test_parametros_invalidos_son_422(self, banco, params):
        assert (await pagina(params)).status_code == 422


class TestEscapeYSoloLectura:

    async def test_un_nombre_con_html_se_muestra_escapado(self, banco):
        malo = "<img src=x onerror=alert(1)> 01.cbz"
        await banco.sembrar(archivo(f"Comics/<b>Carpeta</b>/{malo}"))
        cuerpo = (await pagina()).text
        assert "<img src=x" not in cuerpo and "<b>Carpeta</b>" not in cuerpo
        assert htmllib.escape(malo) in cuerpo or "&lt;img src=x onerror=alert(1)&gt;" in cuerpo

    async def test_cero_escrituras_y_cero_disco(self, banco, monkeypatch):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Sin/Cosa 01.cbz"),
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct", cands=candidatas(sid, "BATMAN", 2025)),
        )
        await pagina()                                          # calienta conexión y plantillas
        tablas = ("files", "series", "issues", "import_runs", "asignacion_operaciones", "local_aliases")

        async def huella():
            async with banco.fabrica() as s:
                return {t: tuple((await s.execute(text(
                    f"SELECT count(*), md5(coalesce(string_agg(x::text, '|' ORDER BY x::text), '')) FROM {t} x"
                ))).one()) for t in tablas}
        antes = await huella()
        accesos: list[str] = []

        def vigilar(modulo, nombre):
            real = getattr(modulo, nombre)

            def vigilado(p, *a, **k):
                if str(p).startswith(BIB):
                    accesos.append(f"{nombre}({p})")
                    raise AssertionError(f"{nombre} sobre la biblioteca: {p}")
                return real(p, *a, **k)
            monkeypatch.setattr(modulo, nombre, vigilado)
        for nombre in ("stat", "lstat", "scandir", "listdir"):
            vigilar(os, nombre)
        for nombre in ("exists", "is_file", "stat", "iterdir", "resolve"):
            vigilar(Path, nombre)
        vigilar(builtins, "open")

        banco.sentencias.clear()
        r = await pagina()
        assert r.status_code == 200 and accesos == []
        assert banco.sentencias and all(s.lstrip().upper().startswith(("SELECT", "WITH")) for s in banco.sentencias)
        assert len(banco.sentencias) <= 3
        assert await huella() == antes


class TestAccesoYEnlaces:

    async def test_sin_sesion_no_hay_datos(self, banco, monkeypatch):
        from zascarr.config import get_settings
        from zascarr.services.auth import hash_password
        ajustes = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: ajustes)
        await banco.sembrar(archivo("Comics/Sin/CosaSecretaQ9 01.cbz"))
        async with cliente(follow_redirects=False) as c:
            r = await c.get(RUTA)
        assert r.status_code in (302, 303, 307) and "/login" in r.headers["location"]
        assert "CosaSecretaQ9" not in r.text

    async def test_por_revisar_enlaza_a_la_vista_por_carpetas(self, banco):
        await banco.sembrar(archivo("Comics/Sin/Cosa 01.cbz"))
        r = await pagina(ruta="/ui/pendientes")
        assert r.status_code == 200 and 'href="/ui/pendientes/carpetas"' in r.text

    async def test_la_vista_enlaza_de_vuelta(self, banco):
        r = await pagina()
        assert 'href="/ui/pendientes"' in r.text
