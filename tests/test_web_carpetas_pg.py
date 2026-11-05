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
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import structlog.testing
from sqlalchemy import text

import zascarr.web.pendientes as _pendientes
from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import (
    BIB,
    Banco,
    archivo,
    candidatas,
    sembrar_referencia_u13a,
)
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import revision_carpetas, runtime_settings
from zascarr.services.registro_biblioteca import EstadoRegistro as _EstadoRegistro
from zascarr.services.registro_biblioteca import FaseRegistro as _FaseRegistro
from tests.test_asistente_vinculacion_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    _secreto_en_el_asistente,
)
from tests.test_u19_recorrido_pg import (  # noqa: F401  (fixtures y ayudas compartidas)
    V as V_U19,
    ent,
    entorno,
    get as get_u19,
    url_bd,
    vinculada,
)
from zascarr.services.revision_carpetas import (
    ETIQUETAS,
    ArchivoRevision,
    CarpetaLimpiaOut,
    Grupo,
    Pagina,
    PatronDeNombres,
    RespuestaCarpetas,
    Senal,
    SerieSugerida,
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


def miles(n: int) -> str:
    """El formato de la vista: punto para los miles (1.322), no coma."""
    return f"{n:,}".replace(",", ".")


def _grupo_de_referencia(clave: str, n_archivos: int, sugerida: SerieSugerida | None = None) -> Grupo:
    """Una tarjeta del fixture enlatado de U21; no toca la BD ni el disco."""
    titulo = clave.rsplit("/", 1)[-1]
    return Grupo(
        clave=clave, carpeta_contextual=titulo, ascendentes=["Comics"],
        carpeta_limpia=CarpetaLimpiaOut(titulo=titulo, anio=None, volumen=None, calificadores=[]),
        estado="serie_sugerida" if sugerida else "sin_serie",
        etiqueta=ETIQUETAS["serie_sugerida" if sugerida else "sin_serie"],
        n_archivos=n_archivos,
        patron_de_nombres=PatronDeNombres(titulo_dominante=titulo, proporcion=1.0, titulos_distintos=1),
        serie_sugerida=sugerida, por_confirmar=sugerida is not None, en_conflicto=False,
        senales=[], archivos=[ArchivoRevision(id=f"id-{clave}", nombre=f"{titulo} 01.cbz",
                                              estado="serie_sugerida" if sugerida else "sin_serie")],
    )


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
        assert f"{miles(datos['totales']['sin_serie'])} por revisar" in t
        assert (
            f"{miles(datos['totales']['sin_serie_en_carpetas'])} en "
            f"{miles(datos['totales']['carpetas_utiles_sin_serie'])} carpeta" in t
        )
        assert f"de {miles(datos['totales']['carpetas_utiles'])}" in t

    async def test_la_vista_pinta_lo_que_devuelve_el_servicio_sin_recalcular(self, banco, monkeypatch):
        """Una respuesta ENLATADA con un texto de señal inventado: si la vista lo recalculara, no saldría."""
        enlatada = RespuestaCarpetas(
            generado="2026-10-07T00:00:00Z",
            totales=Totales(
                sin_serie=0, serie_sugerida=1, grupos=1, candidata_inexistente=0,
                carpetas_utiles=1, carpetas_utiles_sin_serie=0,
                carpetas_utiles_serie_sugerida=1, sin_serie_en_carpetas=0,
                sin_serie_sueltos=0, serie_sugerida_en_carpetas=1,
                serie_sugerida_sueltos=0, sueltos=0,
            ),
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

        async def falso(self, limite=200, desplazamiento=0, solo_utiles=False, **_kwargs):
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
        # BL-FILT1: la pantalla sigue sin acciones que ESCRIBAN. Se permite UN formulario GET
        # (el filtro) con UN botón de envío; nada de JS ni de HTMX ni de formularios POST.
        for prohibido in ("<script", "hx-post", "hx-delete", "hx-put", "hx-get", "onclick", "onerror="):
            assert prohibido not in cuerpo, prohibido
        assert cuerpo.count("<form") == 1
        formulario = re.search(r"<form\b[^>]*>", cuerpo).group(0)
        assert 'method="get"' in formulario and 'action="/ui/pendientes/carpetas"' in formulario
        assert cuerpo.count('type="submit"') == 1
        for metodo in ("post", "put", "delete", "patch"):
            assert f'method="{metodo}"' not in cuerpo
        # #118: lo único nuevo es un ENLACE por carpeta al asistente (abrirlo no consulta ni escribe nada).
        assert cuerpo.count('href="/ui/pendientes/carpetas/asistente?clave=') == 2
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


class TestU13aCarpetasUtilesYSueltos:
    """La vista lista solo grupos con contexto y deja los sueltos accesibles."""

    async def test_solo_pinta_carpetas_utiles_y_enlaza_los_sueltos(self, banco):
        await banco.sembrar(
            archivo("Comics/G/Cosa 01.cbz"),
            archivo("Comics/Suelto 01.cbz"),
        )
        r = await pagina()
        t = visible(r.text)
        assert "Comics/G" in t
        assert "Comics/Suelto" not in t
        assert re.search(r"2 por revisar: 1 en 1 carpeta \+ 1 suelto\s*\.", t)
        assert 'href="/ui/pendientes"' in r.text and ">1 suelto</a>" in r.text
        assert "No hay carpetas con contexto" not in t

    async def test_la_api_sin_filtro_incluye_el_grupo_sin_contexto_y_la_vista_lo_excluye(self, banco):
        await banco.sembrar(
            archivo("Comics/G/Cosa 01.cbz"),
            archivo("Comics/Suelto 01.cbz"),
        )
        async with cliente() as c:
            datos = (await c.get("/api/revision/carpetas")).json()
            html = (await c.get(RUTA)).text
        grupos = {g["clave"]: g for g in datos["grupos"]}
        assert grupos["Comics"]["carpeta_contextual"] is None
        assert [a["nombre"] for a in grupos["Comics"]["archivos"]] == ["Suelto 01.cbz"]
        assert "Comics/Suelto" not in visible(html)

    async def test_el_recuento_del_enlace_no_cuenta_sueltos(self, banco):
        await banco.sembrar(
            archivo("Comics/G/Cosa 01.cbz"),
            archivo("Comics/Suelto 01.cbz"),
            archivo("Raiz 01.cbz"),
        )
        async with cliente() as c:
            r = await c.get("/ui/pendientes/carpetas/recuento")
        texto = " ".join(htmllib.unescape(re.sub(r"<[^>]+>", " ", r.text)).split())
        assert r.status_code == 200
        assert texto == "Verlos por carpeta (1 carpeta)"

    async def test_una_pagina_que_ya_no_existe_tiene_salida(self, banco):
        await banco.sembrar(*(archivo(f"Comics/G{i}/Cosa 01.cbz") for i in range(5)))
        r = await pagina({"limite": 2, "desplazamiento": 99})
        t = visible(r.text)
        assert "Esta página ya no existe" in t
        assert "Ir a la primera página" in t and "Ir a la última página válida" in t
        assert "Carpetas 99–99" not in t
        assert 'href="/ui/pendientes/carpetas?limite=2"' in r.text
        assert "desplazamiento=4" in r.text

    async def test_solo_sueltos_dice_que_no_hay_carpetas_y_deja_la_salida(self, banco):
        await banco.sembrar(archivo("Comics/Suelto 01.cbz"), archivo("Raiz 01.cbz"))
        r = await pagina()
        t = visible(r.text)
        assert re.search(r"2 por revisar: 0 en 0 carpetas \+ 2 sueltos\s*\.", t)
        assert "No hay carpetas con contexto" in t
        assert 'href="/ui/pendientes"' in r.text and ">2 sueltos</a>" in r.text
        assert "Nada pendiente" not in t

    async def test_un_fallo_no_pinta_recuentos_parciales(self, banco, monkeypatch):
        await banco.sembrar(archivo("Comics/G/CosaSecretaQ9 01.cbz"))

        async def roto(self, *args, **kwargs):
            raise RuntimeError("fallo de lectura")

        monkeypatch.setattr(revision_carpetas.RevisionCarpetas, "carpetas", roto)
        r = await pagina()
        t = visible(r.text)
        assert r.status_code == 503
        assert "No se han podido leer los pendientes" in t
        assert "No se muestran recuentos parciales" in t
        assert "CosaSecretaQ9" not in t and "1 por revisar" not in t
        assert 'href="/ui/pendientes/carpetas?limite=50">Reintentar</a>' in r.text

    async def test_medicion_local_de_carga_y_cambio_de_pagina(self, banco):
        """P1/P1b locales en ASGI con 1.322 A + 17 B, página 50.

        No es la medición de navegador real ni de la Pi: P1/P1b/P4 siguen NOT RUN.
        """
        import time

        await sembrar_referencia_u13a(banco)
        async with cliente() as c:
            await c.get(RUTA, params={"limite": 50})             # calienta

            banco.sentencias.clear()
            primera = await c.get(RUTA, params={"limite": 50})
            consultas = len(banco.sentencias)
            assert primera.status_code == 200
            assert primera.text.count('class="card carpeta"') == 50

            tiempos_primera: list[float] = []
            for _ in range(20):
                inicio = time.perf_counter()
                await c.get(RUTA, params={"limite": 50})
                tiempos_primera.append((time.perf_counter() - inicio) * 1000)

            cambio = await c.get(RUTA, params={"limite": 50, "desplazamiento": 50})
            assert cambio.status_code == 200
            assert cambio.text.count('class="card carpeta"') == 50
            tiempos_cambio: list[float] = []
            for _ in range(20):
                inicio = time.perf_counter()
                await c.get(RUTA, params={"limite": 50, "desplazamiento": 50})
                tiempos_cambio.append((time.perf_counter() - inicio) * 1000)

        p95_primera = sorted(tiempos_primera)[18]
        p95_cambio = sorted(tiempos_cambio)[18]
        assert consultas <= 3, consultas
        assert p95_primera <= 2000, f"p95 primera {p95_primera:.0f} ms"
        assert p95_cambio <= 1000, f"p95 cambio {p95_cambio:.0f} ms"
        print(f"\n[U13a] HTML local 1.322+17, página 50: {consultas} consultas; "
              f"p95 primera {p95_primera:.0f} ms, p95 cambio {p95_cambio:.0f} ms "
              f"(ASGI, no navegador/Pi)")


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


class TestPresupuestoTexto:
    """U21: la entrada y los datos de decisión caben antes de la primera acción de la tarjeta."""

    @staticmethod
    def _palabras(html: str) -> list[str]:
        texto = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", htmllib.unescape(texto)).strip().split()

    @staticmethod
    def _sin_contenido_de_detalles(html: str) -> str:
        """Quita el contenido de <details>, pero conserva el texto visible del <summary>."""
        def resumen(bloque: re.Match[str]) -> str:
            encontrado = re.search(r"<summary\b[^>]*>(.*?)</summary>", bloque.group(0), re.S)
            return encontrado.group(1) if encontrado else " "

        return re.sub(r"<details\b.*?</details>", resumen, html, flags=re.S)

    async def test_entrada_y_primera_accion_caben_en_50_palabras(self, banco):
        """BL-FILT1: la primera acción de la pantalla pasa a ser el formulario de filtro."""
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        cuerpo = (await pagina()).text
        principal_cuerpo = principal(cuerpo).split(">", 1)[1]
        sin_detalles = self._sin_contenido_de_detalles(principal_cuerpo)
        antes = sin_detalles.split("<form", 1)[0]
        palabras = self._palabras(antes)
        assert len(palabras) <= 50, f"{len(palabras)} palabras antes de la acción: {' '.join(palabras)}"
        assert "No se crea ni se asigna nada hasta que confirmes." in visible(cuerpo)
        assert "Sin serie sugerida" in principal_cuerpo
        assert principal_cuerpo.index('class="carpeta-accion"') < principal_cuerpo.index('class="carpeta-detalle"')

    async def test_la_cabecera_sin_filtro_cabe_en_50_palabras_con_el_fixture_de_referencia(self, banco, monkeypatch):
        """U13a medía 46 palabras antes de la acción de la tarjeta; con BL-FILT1 la primera acción
        es el formulario de filtro, así que se conserva el umbral (≤ 50), no la cifra exacta
        (spec §10.2). El fixture se mantiene para que la respuesta enlatada siga siendo la de
        referencia (1.322 A + 17 B, 108 carpetas útiles).
        """
        enlatada = RespuestaCarpetas(
            generado="2026-10-21T00:00:00Z",
            totales=Totales(
                sin_serie=1322, serie_sugerida=17, grupos=108, candidata_inexistente=0,
                carpetas_utiles=108, carpetas_utiles_sin_serie=108,
                carpetas_utiles_serie_sugerida=1, sin_serie_en_carpetas=1308,
                sin_serie_sueltos=14, serie_sugerida_en_carpetas=17,
                serie_sugerida_sueltos=0, sueltos=14,
            ),
            pagina=Pagina(limite=50, desplazamiento=0),
            grupos=[
                _grupo_de_referencia("Comics/Flash (1987)", 155),
                _grupo_de_referencia(
                    "Comics/Batman (2016)", 42,
                    SerieSugerida(series_id="id-batman", titulo="Batman", anio=2016, puntuacion=0.92)),
            ],
        )

        async def falso(self, limite=200, desplazamiento=0, solo_utiles=False, **_kwargs):
            return enlatada
        monkeypatch.setattr(revision_carpetas.RevisionCarpetas, "carpetas", falso)

        cuerpo = (await pagina()).text
        principal_cuerpo = principal(cuerpo).split(">", 1)[1]
        sin_detalles = self._sin_contenido_de_detalles(principal_cuerpo)
        antes = sin_detalles.split("<form", 1)[0]
        palabras = self._palabras(antes)
        assert len(palabras) <= 50, f"{len(palabras)} palabras: {' '.join(palabras)}"

    async def test_estado_vacio_tambien_cabe(self, banco):
        cuerpo = (await pagina()).text
        principal_cuerpo = principal(cuerpo).split(">", 1)[1]
        antes = principal_cuerpo.split("<form", 1)[0]
        assert len(self._palabras(antes)) <= 50

    async def test_el_subtitulo_no_pasa_de_20_palabras(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        cuerpo = (await pagina()).text
        subtitulo = re.search(r'<p class="subtitle">(.*?)</p>', cuerpo, re.S).group(1)
        assert len(self._palabras(subtitulo)) == 18      # la frase aprobada, ≤ 20

    async def test_el_recuento_con_filtro_no_pasa_de_20_palabras(self, banco):
        await banco.sembrar(
            *(archivo(f"Comics/Coincide {i:02d}/Cosa 01.cbz") for i in range(7)),
            *(archivo(f"Comics/Otra {i:03d}/Cosa 01.cbz") for i in range(113)),
        )
        cuerpo = (await pagina({"nombre": "coincide"})).text
        recuento = re.search(r'<p class="subtitle" id="recuento-filtro">(.*?)</p>', cuerpo, re.S).group(1)
        assert len(self._palabras(recuento)) <= 20
        assert "Quitar el filtro" in recuento


class TestFormularioDeFiltro:
    """§5.1: textos exactos, etiquetas visibles y UN formulario GET accesible."""

    async def test_textos_y_estructura_del_formulario(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        html = (await pagina()).text
        formulario = re.search(r'<form class="filter-bar".*?</form>', html, re.S).group(0)
        for exacto in ("Nombre de la carpeta", "Parte del nombre", "Estado de la carpeta",
                       "Todas", "Sin serie", "Con serie sugerida",
                       "Mezcla (sin serie y con serie sugerida)", "Marcas", "Por confirmar",
                       "En conflicto", "Se suman al estado; no son estados.", "Filtrar"):
            assert exacto in formulario, exacto
        assert 'method="get"' in formulario and 'action="/ui/pendientes/carpetas"' in formulario
        # Etiquetas visibles asociadas y campo de búsqueda nativo.
        assert 'for="f-nombre"' in formulario and 'id="f-nombre"' in formulario
        assert 'for="f-estado"' in formulario and 'id="f-estado"' in formulario
        assert 'type="search"' in formulario and 'name="nombre"' in formulario
        assert "<legend>Marcas</legend>" in formulario
        # Los hidden van antes que los campos visibles (GET serializa en ese orden).
        assert formulario.index('name="limite"') < formulario.index('id="f-nombre"')
        # Sin desplazamiento: aplicar el filtro vuelve a la página 1.
        assert 'name="desplazamiento"' not in formulario

    async def test_el_valor_y_las_marcas_se_recuerdan(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        html = (await pagina({"nombre": "cosa", "estado": "sin_serie",
                              "por_confirmar": "1", "en_conflicto": "1"})).text
        formulario = re.search(r'<form class="filter-bar".*?</form>', html, re.S).group(0)
        assert 'value="cosa"' in formulario
        assert re.search(r'<option value="sin_serie" selected>', formulario)
        assert _marcada(formulario, "por_confirmar") and _marcada(formulario, "en_conflicto")


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


# ── #304 BL-SER2: serie fijada, marca, paginación y #326 ─────────────────────────────────────


async def _poner_marcador(banco: Banco, valor: bool) -> None:
    async with banco.fabrica() as s:
        await s.execute(text(
            'INSERT INTO runtime_settings (id, "values") VALUES (1, CAST(:v AS jsonb)) '
            'ON CONFLICT (id) DO UPDATE SET "values" = CAST(:v AS jsonb)'
        ), {"v": json.dumps({"_library_adoption_done": valor})})
        await s.commit()


async def _borrar_marcador(banco: Banco) -> None:
    async with banco.fabrica() as s:
        await s.execute(text("DELETE FROM runtime_settings WHERE id = 1"))
        await s.commit()


CHIP_SUGERIDA = r'<span class="chip[^"]*">(?:<span[^>]*>.*?</span> )?Sugerida para esta serie</span>'


def _hrefs(html: str) -> list[str]:
    return [htmllib.unescape(h) for h in re.findall(r'href="([^"]+)"', html)]


def _hrefs_del_vacio(html: str) -> list[str]:
    """Los enlaces del bloque de estado vacío: el menú de la página también lleva /ui/auditoria."""
    return _hrefs(re.search(r'<div class="empty-state">.*?</div>', html, re.S).group(0))


class TestSerieFijada:

    async def test_muestra_contexto_y_una_accion_por_carpeta(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Comics/Otra/Cosa 01.cbz"),
        )
        r = await pagina({"serie": str(sid)})
        t = visible(r.text)
        assert "Añadiendo números a BATMAN (2025)." in t
        assert "Quitar la serie" in t and "Ver la ficha" in t
        assert "Preparar los archivos de esta carpeta para esta serie" in t
        assert "Sugerida para esta serie" in t
        # una acción nueva por cada una de las dos carpetas, sin la vieja con serie
        assert len(re.findall(r"/asistente/vinculacion\?clave=", r.text)) == 2
        assert "/asistente?clave=" not in r.text
        assert f"series_id={sid}" in r.text

    async def test_clave_codificada_y_series_id_exacto(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(archivo("Comics/Batman (2019)/Batman 01.cbz",
                                    estado="direct", cands=candidatas(sid, "BATMAN", 2025)))
        r = await pagina({"serie": str(sid)})
        enlaces = [h for h in _hrefs(r.text) if "/asistente/vinculacion?clave=" in h]
        assert len(enlaces) == 1
        assert "clave=Comics/Batman%20%282019%29" in enlaces[0]
        assert f"series_id={sid}" in enlaces[0]

    async def test_una_carpeta_sugerida_para_otra_serie_no_lleva_la_marca(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        otra = await banco.serie("SUPERMAN", 2024)
        await banco.sembrar(archivo("Comics/Superman (2024)/Superman 01.cbz", estado="direct",
                                    cands=candidatas(otra, "SUPERMAN", 2024)))
        con = await pagina({"serie": str(sid)})
        assert "Comics/Superman (2024)" in visible(con.text)          # la carpeta se lista...
        assert not re.search(CHIP_SUGERIDA, con.text)                 # ...pero no es «para esta serie» (la frase suelta
        propia = await pagina({"serie": str(otra)})                   # sale también en la explicación: se mira la marca)
        assert re.search(CHIP_SUGERIDA, propia.text)                  # control: para SU serie sí

    async def test_marca_solo_la_sugerida_y_no_reordena(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Comics/Otra/Cosa 01.cbz"),
        )
        sin = visible((await pagina()).text)
        respuesta = await pagina({"serie": str(sid)})
        con = visible(respuesta.text)
        assert re.search(CHIP_SUGERIDA, respuesta.text)
        # el orden de las claves es el mismo con y sin serie
        claves = ["Comics/Batman (2019)", "Comics/Otra"]
        pos_sin = [sin.index(c) for c in claves]
        pos_con = [con.index(c) for c in claves]
        assert pos_sin == sorted(pos_sin) and pos_con == sorted(pos_con)

    async def test_suelto_y_carpeta_con_contexto(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Suelto.cbz"),
        )
        t = visible((await pagina({"serie": str(sid)})).text)
        assert "Comics/Batman (2019)" in t and "Suelto.cbz" not in t
        assert "Por revisar" in t

    async def test_serie_invalida_y_serie_inexistente_no_rompen(self, banco):
        await banco.sembrar(archivo("Comics/Otra/Cosa 01.cbz"))
        for valor in ("no-es-uuid", str(uuid4())):
            r = await pagina({"serie": valor})
            t = visible(r.text)
            assert r.status_code == 200
            assert "No hemos encontrado esa serie" in t
            assert "series_id=" not in r.text
            assert "Elegir la serie de esta carpeta" in t
            assert "Preparar los archivos" not in t

    async def test_120_carpetas_paginan_y_conservan_serie_y_limite(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(*(archivo(f"Comics/G{i}/Cosa 01.cbz") for i in range(120)))
        primera = await pagina({"serie": str(sid), "limite": 50})
        assert "Carpetas 1–50 de 120" in visible(primera.text)
        enlaces = [h for h in _hrefs(primera.text) if "/ui/pendientes/carpetas?" in h and "desplazamiento=" in h]
        assert enlaces
        assert all("serie=" in h and "limite=50" in h for h in enlaces)
        assert any("desplazamiento=50" in h for h in enlaces)
        segunda = await pagina({"serie": str(sid), "limite": 50, "desplazamiento": 50})
        assert "Carpetas 51–100 de 120" in visible(segunda.text)
        enlaces2 = [h for h in _hrefs(segunda.text) if "/ui/pendientes/carpetas?" in h and "desplazamiento=" in h]
        assert 'rel="first"' in segunda.text                      # Primera
        assert any("desplazamiento=100" in h for h in enlaces2)    # Última
        assert all("serie=" in h and "limite=50" in h for h in enlaces2)

    async def test_pagina_fuera_de_rango_conserva_serie(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        r = await pagina({"serie": str(sid), "desplazamiento": 999})
        t = visible(r.text)
        assert "Esta página ya no existe" in t
        quitar_serie = re.findall(r'href="([^"]+)"[^>]*>Quitar la serie</a>', r.text)
        assert len(quitar_serie) == 1, quitar_serie
        enlaces = [h for h in _hrefs(r.text) if "/ui/pendientes/carpetas?" in h
                   and h not in quitar_serie]
        assert enlaces and all("serie=" in h for h in enlaces), enlaces

    async def test_sin_serie_no_aparecen_primera_ni_ultima(self, banco):
        await banco.sembrar(*(archivo(f"Comics/G{i}/Cosa 01.cbz") for i in range(5)))
        r = await pagina({"limite": 2, "desplazamiento": 2})
        assert "Primera" not in visible(r.text) and "Última" not in visible(r.text)


class TestVacíoY326:

    async def test_vacio_con_serie_ofrece_326_si_marcador_true(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await _poner_marcador(banco, True)
        r = await pagina({"serie": str(sid)})
        t = visible(r.text)
        assert "No hay carpetas con contexto pendientes" in t
        assert r.text.count('class="empty-state"') == 1
        assert "Buscar archivos nuevos en el disco" in t and "/ui/auditoria" in _hrefs(r.text)
        assert "solo los registra" in t

    async def test_vacio_sin_marcador_dice_registrar_y_no_ofrece_buscar(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await _borrar_marcador(banco)
        r = await pagina({"serie": str(sid)})
        t = visible(r.text)
        assert "Tu biblioteca aún no está registrada, así que ZascArr no puede buscar archivos nuevos." in t
        assert "El registro está en Duplicados, en el apartado «Registrar mi biblioteca»." in t
        assert "No mueve ni renombra ningún archivo." in t
        assert "al final de la página" not in t
        assert r.text.count('class="empty-state"') == 1
        assert "Buscar archivos nuevos en el disco" not in t
        assert "Ir a registrar mi biblioteca" in t and "Ir a Duplicados" not in t
        assert _hrefs_del_vacio(r.text) == ["/ui/pendientes", "/ui/auditoria#registro", "/ui/pendientes"]
        assert "Ir a Por revisar" in t                                               # el secundario no cambia

    async def test_si_no_se_puede_leer_el_marcador_no_afirma_que_no_este_registrada(self, banco, monkeypatch):
        sid = await banco.serie("BATMAN", 2025)
        await _poner_marcador(banco, True)           # lo está: la pantalla no puede decir lo contrario

        async def falla(self, clave):
            raise RuntimeError("lectura del marcador simulada /srv/interno")
        monkeypatch.setattr(runtime_settings.RuntimeSettingsService, "get_flag_sin_crear", falla)
        with structlog.testing.capture_logs() as registro:
            r = await pagina({"serie": str(sid)})
        t = visible(r.text)
        assert r.status_code == 200 and r.text.count('class="empty-state"') == 1
        assert "No se ha podido comprobar si tu biblioteca está registrada. Prueba de nuevo en unos segundos." in t
        assert "aún no está registrada" not in t and "todavía no está registrada" not in t
        assert "Ir a registrar mi biblioteca" not in t and "Buscar archivos nuevos en el disco" not in t
        assert "Ir a Por revisar" in t
        assert _hrefs_del_vacio(r.text) == ["/ui/pendientes", "/ui/pendientes"]      # ni registro ni búsqueda
        assert "/srv/interno" not in r.text and "RuntimeError" not in r.text
        fallos = [e for e in registro if e.get("event") == "pendientes.marcador_fallo"]
        assert len(fallos) == 1 and fallos[0].get("error") == "RuntimeError" and "/srv/interno" not in str(registro)

    async def test_vacio_en_marcha_lo_dice(self, banco, monkeypatch):
        sid = await banco.serie("BATMAN", 2025)
        monkeypatch.setattr(_pendientes.registro_biblioteca, "estado_actual",
                            lambda: _EstadoRegistro(fase=_FaseRegistro.CORRIENDO))
        r = await pagina({"serie": str(sid)})
        assert "Hay un registro en marcha" in visible(r.text)
        assert r.text.count('class="empty-state"') == 1

    @pytest.mark.parametrize("marcador", [True, False])
    async def test_sin_serie_no_aparece_la_oferta_326(self, banco, marcador):
        """Con o sin marcador: si lo pendiente estuviera vacío con la serie fijada saldría la oferta de buscar (marcador) o
        la de registrar (sin él); sin serie no sale ninguna, ni sus enlaces."""
        if marcador:
            await _poner_marcador(banco, True)
        else:
            await _borrar_marcador(banco)
        r = await pagina()
        assert r.status_code == 200
        assert "Buscar archivos nuevos en el disco" not in visible(r.text)
        assert "Ir a registrar mi biblioteca" not in visible(r.text)
        assert "/ui/auditoria#registro" not in _hrefs(r.text)

    async def test_no_crea_la_fila_de_ajustes_al_leer_el_marcador(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await _borrar_marcador(banco)
        async with banco.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM runtime_settings"))).scalar() == 0
        banco.sentencias.clear()
        await pagina({"serie": str(sid)})
        assert banco.sentencias and all(x.lstrip().upper().startswith(("SELECT", "WITH")) for x in banco.sentencias)
        async with banco.fabrica() as s:
            assert (await s.execute(text("SELECT count(*) FROM runtime_settings"))).scalar() == 0

    async def test_no_llama_a_inventario_ni_recorre_disco(self, banco, monkeypatch):
        sid = await banco.serie("BATMAN", 2025)
        await _poner_marcador(banco, True)

        async def prohibido(*_a, **_k):
            raise AssertionError("la lista no debe recorrer la biblioteca")

        import zascarr.services.library_adopter as la
        from zascarr.utils import fs
        monkeypatch.setattr(la.LibraryAdopter, "inventario", prohibido)
        monkeypatch.setattr(fs, "recorrer_comics", prohibido)
        assert (await pagina({"serie": str(sid)})).status_code == 200

    async def test_titulo_se_escapa(self, banco):
        sid = await banco.serie("<b>BATMAN</b>", 2025)
        r = await pagina({"serie": str(sid)})
        assert "<b>BATMAN</b>" not in r.text
        assert "&lt;b&gt;BATMAN&lt;/b&gt;" in r.text

    async def test_503_con_serie_conserva_el_reintento(self, banco, monkeypatch):
        sid = await banco.serie("BATMAN", 2025)

        async def falla(*_a, **_k):
            raise RuntimeError("fallo simulado")

        monkeypatch.setattr(revision_carpetas.RevisionCarpetas, "carpetas", falla)
        r = await pagina({"serie": str(sid)})
        assert r.status_code == 503
        assert "series_id=" not in r.text
        assert f"/ui/pendientes/carpetas?limite=50&amp;serie={sid}" in r.text


# ── BL-FILT1 (#397): filtro por nombre y estado ─────────────────────────────────────────────────

def claves(cuerpo: str) -> list[str]:
    """Las claves de las carpetas pintadas, en el orden de la página."""
    return [htmllib.unescape(c) for c in re.findall(
        r'class="carpeta-titulo titulo-frase">(.*?)</h2>', cuerpo)]


def _marcada(cuerpo: str, nombre: str) -> bool:
    return re.search(rf'name="{nombre}"[^>]*\bchecked\b', cuerpo) is not None


class TestFiltroPorNombre:
    async def test_ac01_coincidencia_parcial_sin_mayusculas(self, banco):
        await banco.sembrar(
            archivo("Comics/Astérix el Galo/Astérix 01.cbz"),
            archivo("Comics/Batman (2019)/Batman 01.cbz"),
        )
        r = await pagina({"nombre": "ast"})
        assert claves(r.text) == ["Comics/Astérix el Galo"]
        assert 'value="ast"' in r.text
        assert claves((await pagina({"nombre": "ASTÉRIX"})).text) == ["Comics/Astérix el Galo"]
        assert 'value="ASTÉRIX"' in (await pagina({"nombre": "ASTÉRIX"})).text

    async def test_ac02_acentos_y_tildes(self, banco):
        await banco.sembrar(
            archivo("Comics/Astérix/Cosa 01.cbz"),
            archivo("Comics/Año Cero/Cosa 01.cbz"),
            archivo("Comics/Doña Urraca/Cosa 01.cbz"),
        )
        assert claves((await pagina({"nombre": "asterix"})).text) == ["Comics/Astérix"]
        assert claves((await pagina({"nombre": "ano"})).text) == ["Comics/Año Cero"]
        assert claves((await pagina({"nombre": "dona"})).text) == ["Comics/Doña Urraca"]
        assert claves((await pagina({"nombre": "AÑO"})).text) == ["Comics/Año Cero"]

    async def test_ac03_recuentos_del_conjunto_filtrado(self, banco):
        await banco.sembrar(
            *(archivo(f"Comics/Coincide {i:02d}/Cosa 01.cbz") for i in range(7)),
            *(archivo(f"Comics/Otra {i:03d}/Cosa 01.cbz") for i in range(113)),
        )
        r = await pagina({"nombre": "coincide"})
        t = visible(r.text)
        assert "Carpetas 1–7 de 7." in t
        assert "7 de 120 carpetas coinciden con el filtro." in t
        assert 'rel="next"' not in r.text
        async with banco.fabrica() as s:
            respuesta = await revision_carpetas.RevisionCarpetas(s).carpetas(
                limite=50, solo_utiles=True, nombre="coincide")
        assert respuesta.filtro is not None
        assert respuesta.filtro.coinciden == 7
        assert respuesta.totales.carpetas_utiles == 120
        assert (respuesta.pagina.limite, len(respuesta.grupos)) == (50, 7)

    async def test_ac04_filtra_sobre_el_titulo_visible_de_la_carpeta(self, banco):
        await banco.sembrar(archivo("Comics/Batman (2019)/Batman 01.cbz"))
        for consulta in ("batman (2019)", "comics batman"):
            assert claves((await pagina({"nombre": consulta})).text) == ["Comics/Batman (2019)"]


class TestFiltroPorEstadoYMarcas:
    async def _sembrar_tres_estados(self, banco) -> None:
        sid = await banco.serie("Sugerida", 2025)
        await banco.sembrar(
            archivo("Comics/Solo Sin/Cosa 01.cbz"),
            archivo("Comics/Solo Sugerida/Sugerida 01 (2025).cbz", estado="direct",
                    cands=candidatas(sid, "Sugerida", 2025)),
            archivo("Comics/Mezcla/Sugerida 01 (2025).cbz", estado="direct",
                    cands=candidatas(sid, "Sugerida", 2025)),
            archivo("Comics/Mezcla/Sin 01.cbz"),
        )

    async def test_ac05_selector_excluyente(self, banco):
        await self._sembrar_tres_estados(banco)
        assert claves((await pagina({"estado": "sin_serie"})).text) == ["Comics/Solo Sin"]
        assert claves((await pagina({"estado": "serie_sugerida"})).text) == ["Comics/Solo Sugerida"]
        assert claves((await pagina({"estado": "mixto"})).text) == ["Comics/Mezcla"]
        todos = claves((await pagina()).text)
        assert set(todos) == {"Comics/Solo Sin", "Comics/Solo Sugerida", "Comics/Mezcla"}
        assert claves((await pagina({"estado": "todas"})).text) == todos
        assert claves((await pagina({"estado": ""})).text) == todos

    async def test_ac06_nombre_y_estado_se_combinan_con_y(self, banco):
        sid = await banco.serie("Batman", 2025)
        await banco.sembrar(
            archivo("Comics/Batman (2019)/Batman 01.cbz", estado="direct",
                    cands=candidatas(sid, "Batman", 2025)),
            archivo("Comics/Batman Sin Serie/Batman 02.cbz"),
        )
        r = await pagina({"nombre": "batman", "estado": "sin_serie"})
        assert claves(r.text) == ["Comics/Batman Sin Serie"]
        assert "1 de 2 carpetas coincide con el filtro." in visible(r.text)

    async def test_ac07_mixto_no_es_en_conflicto(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        # (a) mixto sin conflicto: el año del archivo corrobora la serie sugerida.
        await banco.sembrar(
            archivo("Comics/Mezcla Buena/BATMAN 01 (2025).cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Comics/Mezcla Buena/Sin 01.cbz"),
            # (b) mixto con conflicto: la carpeta dice 2019 y la serie empieza en 2025.
            archivo("Comics/BATMAN - Saga (2019)/BATMAN 01.cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Comics/BATMAN - Saga (2019)/Sin 01.cbz"),
            # (d) sin serie sin conflicto.
            archivo("Comics/Sin Serie/Sin 01.cbz"),
        )
        assert set(claves((await pagina({"estado": "mixto"})).text)) == {
            "Comics/Mezcla Buena", "Comics/BATMAN - Saga (2019)"}
        assert claves((await pagina({"en_conflicto": "1"})).text) == ["Comics/BATMAN - Saga (2019)"]
        assert claves((await pagina({"estado": "mixto", "en_conflicto": "1"})).text) == [
            "Comics/BATMAN - Saga (2019)"]
        assert set(claves((await pagina({"por_confirmar": "1"})).text)) == {
            "Comics/Mezcla Buena", "Comics/BATMAN - Saga (2019)"}
        assert "Comics/BATMAN - Saga (2019)" not in claves(
            (await pagina({"estado": "sin_serie"})).text)

    async def test_ac08_dos_marcas_independientes_y_combinacion_contradictoria(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            archivo("Comics/Mezcla Buena/BATMAN 01 (2025).cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Comics/Mezcla Buena/Sin 01.cbz"),
            archivo("Comics/BATMAN - Saga (2019)/BATMAN 01.cbz", estado="direct",
                    cands=candidatas(sid, "BATMAN", 2025)),
            archivo("Comics/BATMAN - Saga (2019)/Sin 01.cbz"),
            archivo("Comics/Sin Serie/Sin 01.cbz"),
        )
        con_por_confirmar = set(claves((await pagina({"por_confirmar": "1"})).text))
        con_conflicto = set(claves((await pagina({"en_conflicto": "1"})).text))
        ambas = set(claves((await pagina({"por_confirmar": "1", "en_conflicto": "1"})).text))
        assert con_por_confirmar == {"Comics/Mezcla Buena", "Comics/BATMAN - Saga (2019)"}
        assert con_conflicto == {"Comics/BATMAN - Saga (2019)"}
        assert ambas == {"Comics/BATMAN - Saga (2019)"}
        contradictoria = await pagina({"estado": "sin_serie", "por_confirmar": "1"})
        assert contradictoria.status_code == 200
        assert "Ninguna carpeta coincide con estos filtros." in visible(contradictoria.text)


class TestVacioDelFiltro:
    async def test_ac09_estado_vacio_de_filtro(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        r = await pagina({"nombre": "zzz-inexistente"})
        t = visible(r.text)
        assert r.status_code == 200
        assert "Ninguna carpeta coincide con «zzz-inexistente»." in t
        assert "Prueba a cambiar el filtro o a quitarlo." in t
        assert "Nada pendiente" not in t and "No hay carpetas con contexto" not in t
        assert any("Quitar el filtro" in h or "Quitar el filtro" in visible(r.text) for h in _hrefs(r.text))

    async def test_ac10_el_vacio_de_filtro_manda_sobre_el_de_serie(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        r = await pagina({"serie": str(sid), "nombre": "zzz-inexistente"})
        t = visible(r.text)
        assert "Ninguna carpeta coincide con «zzz-inexistente»." in t
        assert "Buscar archivos nuevos en el disco" not in t
        quitar = re.findall(r'href="([^"]+)"[^>]*>Quitar el filtro</a>', r.text)
        assert quitar and f"serie={sid}" in quitar[0] and "nombre=" not in quitar[0]


class TestPropagacionDelContexto:
    async def _sembrar_120(self, banco) -> object:
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(
            *(archivo(f"Comics/Coincide {i:02d}/Cosa 01.cbz") for i in range(25)),
            *(archivo(f"Comics/Otra {i:03d}/Cosa 01.cbz") for i in range(95)),
        )
        return sid

    async def test_ac11_la_paginacion_conserva_el_filtro(self, banco):
        await banco.sembrar(
            *(archivo(f"Comics/Coincide {i:02d}/Cosa 01.cbz") for i in range(25)),
            *(archivo(f"Comics/Otra {i:03d}/Cosa 01.cbz") for i in range(95)),
        )
        r = await pagina({"nombre": "coincide", "limite": 10, "desplazamiento": 10})
        t = visible(r.text)
        assert "Carpetas 11–20 de 25." in t
        enlaces = [h for h in _hrefs(r.text) if "desplazamiento=" in h and "nombre=coincide" in h]
        assert enlaces and all("limite=10" in h for h in enlaces)
        assert any("desplazamiento=0" in h for h in enlaces)          # Anteriores
        assert any("desplazamiento=20" in h for h in enlaces)         # Siguientes

    async def test_ac12_volver_del_asistente_conserva_filtro_pagina_y_serie(self, banco, monkeypatch):
        from types import SimpleNamespace
        from zascarr.config import get_settings
        from zascarr.services import vinculacion_previa
        # La vista previa de la vinculación resuelve la biblioteca por su cuenta y firma con
        # `secret_key`; en pruebas no hay clave y la biblioteca es la de prueba (BIB).
        monkeypatch.setattr(vinculacion_previa, "get_settings",
                            lambda: SimpleNamespace(library_path=Path(BIB)))
        monkeypatch.setattr(
            "zascarr.web.asistente_vinculacion.get_settings",
            lambda: get_settings().model_copy(update={"secret_key": "secreto-de-prueba"}))
        sid = await self._sembrar_120(banco)
        # Con serie fijada la entrada es «Preparar los archivos…» (vinculación).
        lista = await pagina({"nombre": "coincide", "limite": 10, "desplazamiento": 10,
                              "serie": str(sid), "estado": "sin_serie"})
        enlaces = [h for h in _hrefs(lista.text) if "/asistente/vinculacion?clave=" in h]
        assert enlaces, "la lista filtrada no enlaza a la vinculación"
        vinculacion = enlaces[0]
        for esperado in ("nombre=coincide", "limite=10", "desplazamiento=10",
                         f"serie={sid}", "estado=sin_serie"):
            assert esperado in vinculacion, (esperado, vinculacion)
        r2 = await pagina(ruta=vinculacion)
        assert r2.status_code == 200
        vuelta = [h for h in _hrefs(r2.text) if h.startswith("/ui/pendientes/carpetas?")]
        assert any(all(x in h for x in ("nombre=coincide", "limite=10",
                                        "desplazamiento=10", f"serie={sid}")) for h in vuelta)
        # La cadena intermedia (formularios POST del asistente) también transporta el contexto.

        acciones = re.findall(r'(?:action|hx-post)="([^"]+)"', r2.text)
        assert acciones and all("nombre=coincide" in a for a in acciones if "/asistente/" in a)
        ocultos = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', r2.text))
        assert ocultos.get("nombre") == "coincide" and ocultos.get("limite") == "10"

        # Sin serie, la entrada es «Elegir la serie de esta carpeta».
        lista2 = await pagina({"nombre": "coincide", "limite": 10, "desplazamiento": 10})
        enlaces2 = [h for h in _hrefs(lista2.text)
                    if "/ui/pendientes/carpetas/asistente?clave=" in h]
        assert enlaces2, "la lista filtrada no enlaza al asistente"
        entrada = enlaces2[0]
        for esperado in ("nombre=coincide", "limite=10", "desplazamiento=10"):
            assert esperado in entrada, (esperado, entrada)
        r3 = await pagina(ruta=entrada)
        assert r3.status_code == 200
        vuelta3 = [h for h in _hrefs(r3.text) if h.startswith("/ui/pendientes/carpetas?")]
        assert vuelta3
        assert any(all(x in h for x in ("nombre=coincide", "limite=10",
                                        "desplazamiento=10")) for h in vuelta3)
        # El formulario de buscar en el asistente lleva el contexto al POST.
        assert any("nombre=coincide" in a for a in re.findall(r'hx-post="([^"]+)"', r3.text))

    async def test_ac13_no_hay_parametro_de_retorno_en_la_lista_ni_en_el_asistente(self, banco):
        sid = await self._sembrar_120(banco)
        lista = await pagina({"nombre": "coincide", "limite": 10, "desplazamiento": 10,
                              "serie": str(sid)})
        asistente = await pagina(ruta="/ui/pendientes/carpetas/asistente?clave=Comics/Coincide 00"
                                 "&nombre=coincide&limite=10&desplazamiento=10")
        for prohibido in ("volver=", "next=", "return_to=", "redirect=", "url="):
            assert prohibido not in lista.text, prohibido
            assert prohibido not in asistente.text, prohibido

    async def test_ac14_quitar_serie_y_quitar_filtro_se_respetan(self, banco):
        sid = await banco.serie("BATMAN", 2025)
        await banco.sembrar(archivo("Comics/Batman cosa/Cosa 01.cbz"))
        r = await pagina({"serie": str(sid), "nombre": "batman", "limite": 50})
        quitar_serie = [h for h in _hrefs(r.text) if h.startswith("/ui/pendientes/carpetas?")
                        and "serie=" not in h and "nombre=batman" in h]
        assert quitar_serie and "desplazamiento" not in quitar_serie[0]
        quitar_filtro = [h for h in _hrefs(r.text) if h.startswith("/ui/pendientes/carpetas?")
                         and "serie=" in h and "nombre=" not in h]
        assert quitar_filtro and "desplazamiento" not in quitar_filtro[0]

    async def test_ac15_valores_invalidos_dan_200_con_aviso_y_nunca_422(self, banco):
        await banco.sembrar(archivo("Comics/Astérix/Cosa 01.cbz"))
        for params in ({"estado": "inventado"}, {"estado": "SIN_SERIE"},
                       {"por_confirmar": "2"}, {"en_conflicto": "abc"}):
            r = await pagina(params)
            assert r.status_code == 200, params
        r = await pagina({"estado": "inventado"})
        assert "El estado de la carpeta no es válido; se muestran todos los estados." in visible(r.text)
        assert not _marcada(r.text, "por_confirmar")
        # El nombre se sigue aplicando aunque el estado sea inválido.
        r = await pagina({"estado": "inventado", "nombre": "asterix"})
        assert claves(r.text) == ["Comics/Astérix"]

    async def test_ac16_texto_del_nombre_controles_longitud_y_escape(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        controles = await pagina({"nombre": "Bat\x00man"})
        assert controles.status_code == 200
        assert "La búsqueda tenía caracteres no válidos; se han quitado." in visible(controles.text)
        larga = await pagina({"nombre": "x" * 250})
        assert "La búsqueda era demasiado larga; se han usado los primeros 200 caracteres." in visible(larga.text)
        maliciosa = await pagina({"nombre": "<script>alert(1)</script>"})
        assert maliciosa.status_code == 200
        assert "<script>" not in maliciosa.text
        assert "&lt;script&gt;" in maliciosa.text

    async def test_ac17_desplazamiento_fuera_de_rango_tras_filtrar(self, banco):
        await banco.sembrar(*(archivo(f"Comics/Coincide {i}/Cosa 01.cbz") for i in range(5)))
        r = await pagina({"nombre": "coincide", "limite": 2, "desplazamiento": 99})
        t = visible(r.text)
        assert r.status_code == 200
        assert "Esta página ya no existe" in t
        assert "Carpetas 99–99" not in t
        primera = [h for h in _hrefs(r.text) if "nombre=coincide" in h and "desplazamiento" not in h]
        assert primera, "no hay enlace a la primera página filtrada"
        ultima = [h for h in _hrefs(r.text) if "nombre=coincide" in h and "desplazamiento=4" in h]
        assert ultima, "no hay enlace a la última página filtrada"

    async def test_ac18_cambiar_filtro_vuelve_a_la_pagina_1(self, banco):
        await banco.sembrar(
            *(archivo(f"Comics/Coincide {i:02d}/Cosa 01.cbz") for i in range(25)),
            *(archivo(f"Comics/Otra {i:03d}/Cosa 01.cbz") for i in range(95)),
        )
        r = await pagina({"nombre": "coincide", "limite": 10, "desplazamiento": 10})
        formulario = re.search(r'<form class="filter-bar".*?</form>', r.text, re.S).group(0)
        assert 'name="desplazamiento"' not in formulario
        assert 'action="/ui/pendientes/carpetas"' in formulario
        assert 'method="get"' in formulario
        quitar = re.findall(r'href="([^"]+)"[^>]*>Quitar el filtro</a>', r.text)
        assert quitar and "desplazamiento" not in quitar[0]


class TestSerieInventadaEnElContexto:
    async def test_una_serie_no_uuid_no_se_propaga_al_asistente(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        invalida = await pagina(ruta="/ui/pendientes/carpetas/asistente?clave=Comics/G"
                                "&nombre=x&serie=no-es-uuid")
        assert invalida.status_code == 200
        assert "no-es-uuid" not in invalida.text
        assert 'name="serie" value="no-es-uuid"' not in invalida.text

        from uuid import uuid4
        sid = uuid4()
        valida = await pagina(ruta=f"/ui/pendientes/carpetas/asistente?clave=Comics/G"
                              f"&nombre=x&serie={sid}")
        assert valida.status_code == 200
        assert f'name="serie" value="{sid}"' in valida.text


class TestResultadoGuardadoNoPropaga:
    """§6.4: el resultado guardado es la excepción; con una referencia VÁLIDA tampoco propaga."""

    async def test_ac13_un_resultado_guardado_valido_no_propaga_el_contexto(self, ent):
        v = await vinculada(ent)
        consulta = {"ref": v.ref, "nombre": "batman", "estado": "sin_serie",
                    "por_confirmar": "1", "en_conflicto": "1", "limite": "10",
                    "desplazamiento": "20"}
        r = await get_u19(f"{V_U19}/resultado", **consulta)
        assert r.status_code == 200
        assert "Resultado de la vinculación" in visible(r.text)
        enlaces = [h for h in _hrefs(r.text) if "/ui/pendientes/carpetas" in h]
        assert enlaces, "el resultado guardado no tiene enlaces de vuelta a la lista"
        for h in enlaces:
            for parametro in ("nombre=batman", "estado=sin_serie", "por_confirmar=1",
                              "en_conflicto=1", "limite=10", "desplazamiento=20"):
                assert parametro not in h, (parametro, h)
        # Contrato de hoy: «Volver a las carpetas» sin parámetros y «Elegir otra carpeta»
        # solo con `serie`.
        assert any(h == "/ui/pendientes/carpetas" for h in enlaces)
        assert any(re.fullmatch(r"/ui/pendientes/carpetas\?serie=[0-9a-f-]+", h) for h in enlaces)

        async with cliente() as c:
            fragmento = await c.get(f"{V_U19}/resultado", params=consulta,
                                    headers={"HX-Request": "true"})
        assert fragmento.status_code == 200
        assert "nombre=batman" not in fragmento.text
        assert "limite=10" not in fragmento.text


class TestMapaDeEnlacesDelAsistente:
    """§6.3: TODOS los enlaces de vuelta a la lista conservan el contexto, salvo el resultado guardado."""

    PLANTILLAS_CON_CONTEXTO = (
        "asistente_carpeta.html", "_asistente_eleccion.html", "asistente_vinculacion.html",
        "_vinculacion_resultado.html", "asistente_alta.html", "asistente_alta_resultado.html",
    )
    def test_cada_plantilla_de_vuelta_usa_el_helper_de_contexto(self):
        base = Path(__file__).resolve().parents[1] / "src/zascarr/web/templates"
        for nombre in self.PLANTILLAS_CON_CONTEXTO:
            texto = (base / nombre).read_text(encoding="utf-8")
            assert "con_contexto(" in texto, f"{nombre} no reenvía el contexto de la lista"

    def test_el_resultado_guardado_desactiva_el_contexto_en_la_ruta(self):
        """La excepción del PO (§6.4) no cambia las plantillas: se apaga en la ruta, que es la
        única que se puede abrir con una `ref` de 24 h y sin la lista delante."""
        fuente = (Path(__file__).resolve().parents[1]
                  / "src/zascarr/web/asistente_vinculacion.py").read_text(encoding="utf-8")
        assert "request.state.sin_contexto_carpetas = True" in fuente

    async def test_ningun_enlace_de_la_lista_sale_a_una_url_absoluta(self, banco):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        html = (await pagina({"nombre": "cosa"})).text
        assert all(not h.startswith(("http://", "https://")) for h in _hrefs(html))


class TestPrivacidadDelFiltro:
    async def test_ac22_el_valor_del_filtro_no_llega_a_los_registros(self, banco, monkeypatch):
        await banco.sembrar(archivo("Comics/G/Cosa 01.cbz"))
        with structlog.testing.capture_logs() as registros:
            r = await pagina({"nombre": "CENTINELA-PRIV-9Q", "estado": "inventado"})
        assert r.status_code == 200
        assert "CENTINELA-PRIV-9Q" not in repr(registros)

        async def falla(*_a, **_k):
            raise RuntimeError("fallo simulado")

        monkeypatch.setattr(revision_carpetas.RevisionCarpetas, "carpetas", falla)
        with structlog.testing.capture_logs() as registros_fallo:
            r = await pagina({"nombre": "CENTINELA-PRIV-9Q"})
        assert r.status_code == 503
        assert any(reg.get("event") == "pendientes.carpetas_fallo" for reg in registros_fallo)
        assert "CENTINELA-PRIV-9Q" not in repr(registros_fallo)


class TestArticulosYPuntuacion:
    async def test_ac24_articulos_puntuacion_y_texto_sin_palabras(self, banco):
        await banco.sembrar(
            archivo("Comics/Los Vengadores/Cosa 01.cbz"),
            archivo("Comics/El Sandman/Cosa 01.cbz"),
            archivo("Comics/S.H.I.E.L.D./Cosa 01.cbz"),
        )
        assert claves((await pagina({"nombre": "vengadores"})).text) == ["Comics/Los Vengadores"]
        assert claves((await pagina({"nombre": "sandman"})).text) == ["Comics/El Sandman"]
        assert claves((await pagina({"nombre": "shield"})).text) == ["Comics/S.H.I.E.L.D."]
        for articulo in ("el", "los"):
            r = await pagina({"nombre": articulo})
            assert r.status_code == 200
            assert "El texto no contiene palabras que buscar; no se aplica el filtro de nombre." in visible(r.text)
            assert set(claves(r.text)) == {"Comics/Los Vengadores", "Comics/El Sandman",
                                           "Comics/S.H.I.E.L.D."}
