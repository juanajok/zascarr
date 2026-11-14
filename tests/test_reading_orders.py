# ruff: noqa: E501
"""Extractores de guías SCR3 (AC-02/03/04/05/06/07/09) sin red real.

`httpx.MockTransport` + `CacheHttpFalsa` + los fixtures recortados de `tests/fixtures/lecturas/`.
La caché/robots son los de SCR1; aquí solo se comprueba que el adaptador los usa bien.
"""
from __future__ import annotations

import asyncio
from dataclasses import fields
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from structlog.testing import capture_logs

from tests.test_cache_http import CacheHttpFalsa, Reloj
from zascarr.services.reading_order_resolver import parsear_referencia
from zascarr.services.reading_orders import (
    MAX_CUERPO,
    MAX_GUIAS,
    MAX_REFERENCIA,
    ContinuityGuideExtractor,
    RawReadingEntry,
    ReadingOrdersExtractor,
    parsear_sitemap,
)
from zascarr.services.reading_orders.comun import url_de_item, url_de_sitio_valida
from zascarr.utils.cache_http import reiniciar_candados_para_pruebas
from zascarr.utils.cortesia import CortesiaProceso
from zascarr.utils.robots import GestorRobots

FIXTURES = Path(__file__).parent / "fixtures" / "lecturas"
RO_GUIA = ("https://comicbookreadingorders.com/dc/events/"
           "crisis-on-infinite-earths-reading-order/")
RO_SITEMAP = "https://comicbookreadingorders.com/sitemap.xml"
CG_GUIA = "https://www.continuityguide.net/planetx"
CG_SITEMAP = "https://www.continuityguide.net/sitemap.xml"


def _contenido(nombre: str) -> bytes:
    return (FIXTURES / nombre).read_bytes()


def _html(nombre: str) -> httpx.Response:
    return httpx.Response(200, content=_contenido(nombre),
                          headers={"content-type": "text/html; charset=utf-8"})


def _xml(nombre: str) -> httpx.Response:
    return httpx.Response(200, content=_contenido(nombre),
                          headers={"content-type": "application/xml"})


class Mundo:
    """Transporte falso: cuenta URLs y sirve robots + las rutas indicadas."""

    def __init__(self, rutas: dict[str, httpx.Response | bytes] | None = None):
        self.rutas = rutas or {}
        self.peticiones: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.peticiones.append(url)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /admin/\n")
        for fragmento, respuesta in self.rutas.items():
            if fragmento in url:
                if isinstance(respuesta, bytes):
                    return httpx.Response(200, content=respuesta)
                return respuesta
        return httpx.Response(404)


@pytest.fixture(autouse=True)
def _candados_limpios():
    reiniciar_candados_para_pruebas()
    yield
    reiniciar_candados_para_pruebas()


@pytest.fixture
def fuentes_encendidas(monkeypatch):
    ajustes = SimpleNamespace(
        reading_orders_enabled=True, continuity_guide_enabled=True,
        reading_orders_rate_limit=0.0, continuity_guide_rate_limit=0.0)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.reading_orders.comun.get_settings",
                        lambda: ajustes)
    return ajustes


@pytest.fixture
def fuentes_apagadas(monkeypatch):
    # El default REAL de config.py: las fuentes se estrenan apagadas (ADR 0013).
    from zascarr.config import Settings

    ajustes = Settings(_env_file=None)
    assert ajustes.reading_orders_enabled is False
    assert ajustes.continuity_guide_enabled is False
    monkeypatch.setattr("zascarr.config.get_settings", lambda: ajustes)
    monkeypatch.setattr("zascarr.services.reading_orders.comun.get_settings",
                        lambda: ajustes)
    return ajustes


def _extractor(clase, mundo: Mundo, cache, reloj: Reloj):
    return clase(cache, robots=GestorRobots(reloj=reloj),
                 transporte=httpx.MockTransport(mundo),
                 cortesia=CortesiaProceso(reloj=reloj, dormir=reloj.dormir),
                 reloj=reloj, dormir=reloj.dormir)


def _mundo_ro() -> Mundo:
    return Mundo({"sitemap.xml": _xml("cbro_sitemap.xml"),
                  "crisis-on-infinite-earths": _html("cbro_guia.html")})


def _mundo_cg() -> Mundo:
    return Mundo({"sitemap.xml": _xml("continuity_sitemap.xml"),
                  "planetx": _html("continuity_planetx.html")})


# ── AC-02: RO, orden, secciones y cero prosa ─────────────────────────────────────────────────

async def test_ro_lee_guia_con_orden_secciones_y_enlaces(fuentes_encendidas):
    mundo, reloj, cache = _mundo_ro(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor:
        guia = await extractor.leer_guia(RO_GUIA)
    assert guia is not None
    assert guia.sitio == "reading_orders"
    assert guia.titulo == "Crisis on Infinite Earths Reading Order"
    assert [entrada.orden for entrada in guia.entradas] == list(range(1, 12))
    primera = guia.entradas[0]
    assert primera.referencia == "Green Lantern Vol. 2 #173 (1984)"
    assert primera.seccion == "Prelude"
    assert primera.item_url == "https://www.dcuniverseinfinite.com/comics/green-lantern-173"
    assert [e.seccion for e in guia.entradas[:3]] == ["Prelude"] * 3
    assert guia.entradas[3].seccion == "The Crisis"
    assert guia.entradas[9].referencia == "Justice League Vol. 4 #1"
    assert guia.entradas[9].item_url is None           # ítem sin a.read-link
    # Cero prosa: ni aparece el texto neutro del fixture ni existe campo donde guardarla.
    assert all("PROSA" not in (e.referencia + (e.seccion or "")) for e in guia.entradas)
    assert [campo.name for campo in fields(RawReadingEntry)] == [
        "orden", "referencia", "seccion", "item_url"]


# ── AC-03: CG, tarjetas en orden DOM y exclusiones ───────────────────────────────────────────

async def test_cg_lee_tarjetas_en_orden_y_descarta_prosa(fuentes_encendidas):
    mundo, reloj, cache = _mundo_cg(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ContinuityGuideExtractor, mundo, cache, reloj)
    async with extractor:
        guia = await extractor.leer_guia(CG_GUIA)
    assert guia is not None
    assert [e.referencia for e in guia.entradas] == [
        "Daredevil (1998) #1-8",
        "Daredevil (1998) #9-15",
        "Daredevil (1998) #16-20",
        "Daredevil (1998) #21",
        "Black Widow (1999) #1-3",
        "Incredible Hulk Vol. 2 #1-6",
        "Punisher (2000) #1-4",
    ]
    assert [e.orden for e in guia.entradas] == list(range(1, 8))
    assert all(e.seccion is None for e in guia.entradas)
    assert guia.entradas[1].item_url == "https://www.marvel.com/unlimited/daredevil-9"
    # Fuera: títulos de arco entre comillas y los p con # fuera de tarjeta.
    assert not any("PROSA" in e.referencia for e in guia.entradas)


# ── AC-05: descubrimiento por sitemap, con filtros ───────────────────────────────────────────

async def test_descubrimiento_filtra_los_dos_sitemaps(fuentes_encendidas):
    reloj = Reloj()
    mundo_ro, cache_ro = _mundo_ro(), CacheHttpFalsa()
    extractor_ro = _extractor(ReadingOrdersExtractor, mundo_ro, cache_ro, reloj)
    async with extractor_ro:
        guias_ro = await extractor_ro.descubrir_guias()
    assert len(guias_ro) == 7
    assert {g.sitio for g in guias_ro} == {"reading_orders"}
    assert any("crisis-on-infinite-earths-reading-order" in g.url for g in guias_ro)
    assert all("about" not in g.url and "not-a-guide" not in g.url for g in guias_ro)
    assert guias_ro[0].actualizada == "2026-11-10"

    mundo_cg, cache_cg = _mundo_cg(), CacheHttpFalsa()
    extractor_cg = _extractor(ContinuityGuideExtractor, mundo_cg, cache_cg, reloj)
    async with extractor_cg:
        guias_cg = await extractor_cg.descubrir_guias()
    assert len(guias_cg) == 8
    assert all("images.squarespace-cdn.com" not in g.url for g in guias_cg)
    assert all(g.url.startswith("https://www.continuityguide.net/") for g in guias_cg)


async def test_topes_de_sitemap():
    """10.000 `<loc>` y 2.000 guías: los topes de la spec §2."""
    locs = "".join(
        f"<url><loc>https://comicbookreadingorders.com/dc/events/guia-{i}-reading-order/</loc></url>"
        for i in range(MAX_GUIAS + 505))
    xml = f"<urlset>{locs}</urlset>".encode()
    ficticio = ReadingOrdersExtractor(CacheHttpFalsa())
    guias = parsear_sitemap(xml, ficticio._filtrar_sitemap, "reading_orders")
    assert len(guias) == MAX_GUIAS
    # Tolera namespaces y sitemaps sin <url> envolvente.
    sin_envoltorio = b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><loc>https://comicbookreadingorders.com/dc/events/x-reading-order/</loc></urlset>'
    assert len(parsear_sitemap(sin_envoltorio, ficticio._filtrar_sitemap)) == 1


# ── AC-04: CG nunca usa query ni sitemap_index.xml ───────────────────────────────────────────

async def test_cg_nunca_pide_query_ni_sitemap_index(fuentes_encendidas):
    mundo, reloj, cache = _mundo_cg(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ContinuityGuideExtractor, mundo, cache, reloj)
    async with extractor:
        assert await extractor.leer_guia(CG_GUIA) is not None
        assert await extractor.descubrir_guias()
    assert all("?" not in url for url in mundo.peticiones)
    assert not any("sitemap_index.xml" in url for url in mundo.peticiones)
    assert any(url.endswith("/robots.txt") for url in mundo.peticiones)


# ── AC-06: caché/robots de SCR1 ──────────────────────────────────────────────────────────────

async def test_segunda_lectura_y_segundo_sitemap_salen_de_la_cache(fuentes_encendidas):
    mundo, reloj, cache = _mundo_ro(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor:
        primera = await extractor.leer_guia(RO_GUIA)
        peticiones_tras_guia = len(mundo.peticiones)
        segunda = await extractor.leer_guia(RO_GUIA)
        assert len(mundo.peticiones) == peticiones_tras_guia  # hit sin socket
        await extractor.descubrir_guias()
        peticiones_tras_sitemap = len(mundo.peticiones)
        repetido = await extractor.descubrir_guias()
        assert len(mundo.peticiones) == peticiones_tras_sitemap  # hit del sitemap
    assert segunda == primera
    assert repetido


async def test_ttl_de_guia_sitemap_y_negativa(fuentes_encendidas):
    mundo, reloj, cache = _mundo_ro(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor:
        await extractor.leer_guia(RO_GUIA)
        await extractor.descubrir_guias()
    filas = list(cache.filas.values())
    guia = next(f for f in filas if "crisis-on-infinite-earths" in f.url_canonical)
    assert guia.fresh_until - guia.fetched_at == timedelta(days=14)
    assert guia.retain_until - guia.fetched_at == timedelta(days=74)
    sitemap = next(f for f in filas if f.url_canonical == RO_SITEMAP)
    assert sitemap.fresh_until - sitemap.fetched_at == timedelta(hours=24)
    assert sitemap.retain_until - sitemap.fetched_at == timedelta(days=15)


async def test_negativa_404_no_se_reintenta_y_caduca(fuentes_encendidas):
    mundo = Mundo({"crisis-on-infinite-earths": httpx.Response(404),
                   "sitemap.xml": httpx.Response(404)})
    reloj, cache = Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor:
        assert await extractor.leer_guia(RO_GUIA) is None
        assert await extractor.leer_guia(RO_GUIA) is None
        assert await extractor.descubrir_guias() == []
        assert await extractor.descubrir_guias() == []
    assert len([u for u in mundo.peticiones if "crisis-on-infinite" in u]) == 1
    assert len([u for u in mundo.peticiones if u == RO_SITEMAP]) == 1
    filas = list(cache.filas.values())
    guia = next(f for f in filas if "crisis-on-infinite-earths" in f.url_canonical)
    assert guia.is_negative and guia.fresh_until - guia.fetched_at == timedelta(hours=24)
    sitemap = next(f for f in filas if f.url_canonical == RO_SITEMAP)
    assert sitemap.is_negative and sitemap.fresh_until - sitemap.fetched_at == timedelta(hours=6)


async def test_robots_que_prohibe_devuelve_vacio_y_log_sin_turno(fuentes_encendidas):
    class MundoRobotsProhibe(Mundo):
        def __call__(self, request: httpx.Request) -> httpx.Response:
            self.peticiones.append(str(request.url))
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
            return _html("cbro_guia.html")

    mundo, reloj, cache = MundoRobotsProhibe(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    with capture_logs() as registros:
        async with extractor:
            assert await extractor.leer_guia(RO_GUIA) is None
    assert any(registro["event"] == "reading_orders.sin_turno" for registro in registros)
    assert not any("crisis-on-infinite" in url for url in mundo.peticiones)


async def test_fuente_apagada_devuelve_vacio_sin_peticiones(fuentes_apagadas):
    mundo, reloj, cache = _mundo_ro(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    with capture_logs() as registros:
        async with extractor:
            assert await extractor.leer_guia(RO_GUIA) is None
            assert await extractor.descubrir_guias() == []
    assert mundo.peticiones == []
    assert any(registro["event"] == "reading_orders.sin_turno" for registro in registros)


# ── AC-07: maqueta irreconocible y cuerpo > 2 MiB ───────────────────────────────────────────

async def test_html_irreconocible_devuelve_none_y_log(fuentes_encendidas):
    mundo = Mundo({"crisis-on-infinite-earths": b"<html></html>"})
    reloj, cache = Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    with capture_logs() as registros:
        async with extractor:
            assert await extractor.leer_guia(RO_GUIA) is None
    assert any(registro["event"] == "reading_orders.parse_fallido" for registro in registros)


async def test_cuerpo_demasiado_grande_no_se_parsea(fuentes_encendidas):
    mundo = Mundo({"crisis-on-infinite-earths": b"x" * (MAX_CUERPO + 1)})
    reloj, cache = Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    with capture_logs() as registros:
        async with extractor:
            assert await extractor.leer_guia(RO_GUIA) is None
    assert any(registro["event"] == "reading_orders.cuerpo_demasiado_grande"
               for registro in registros)


# ── URL validada antes de pedir ────────────────────────────────────────────────────────────

async def test_urls_fuera_del_sitio_o_con_query_se_rechazan(fuentes_encendidas):
    mundo, reloj, cache = _mundo_ro(), Reloj(), CacheHttpFalsa()
    extractor_ro = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor_ro:
        assert await extractor_ro.leer_guia("https://evil.example/guia") is None
        assert await extractor_ro.leer_guia(
            "https://comicbookreadingorders.com/api/guia") is None
    assert mundo.peticiones == []          # rechazadas antes de abrir socket

    mundo_cg = _mundo_cg()
    extractor_cg = _extractor(ContinuityGuideExtractor, mundo_cg, cache, reloj)
    async with extractor_cg:
        assert await extractor_cg.leer_guia(f"{CG_GUIA}?format=json") is None
    assert mundo_cg.peticiones == []


# ── AC-09: el parseo va en `asyncio.to_thread` ──────────────────────────────────────────────

async def test_el_parseo_corre_fuera_del_bucle(monkeypatch, fuentes_encendidas):
    real = asyncio.to_thread
    llamadas: list[str] = []

    def espia(func, /, *args, **kwargs):
        llamadas.append(getattr(func, "__name__", str(func)))
        return real(func, *args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", espia)
    mundo, reloj, cache = _mundo_ro(), Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor:
        assert await extractor.leer_guia(RO_GUIA) is not None
        await extractor.descubrir_guias()
    assert "_parsear" in llamadas and "parsear_sitemap" in llamadas


def test_filtro_del_sitemap_cg_excluye_imagenes_y_query():
    extractor = ContinuityGuideExtractor(CacheHttpFalsa())
    assert extractor._filtrar_sitemap("https://www.continuityguide.net/planetx")
    assert not extractor._filtrar_sitemap(
        "https://images.squarespace-cdn.com/content/v1/abc/card1.jpg")
    assert not extractor._filtrar_sitemap(
        "https://www.continuityguide.net/planetx?format=json")


# ── SecOps m-2/m-3/m-4 (condiciones de la entrega 2) ────────────────────────────────────────

def test_m4_parsear_sitemap_con_xml_vacio_o_roto_devuelve_lista():
    filtro = lambda _url: True  # noqa: E731
    assert parsear_sitemap(b"", filtro) == []
    assert parsear_sitemap(b"no es xml", filtro) == []
    assert parsear_sitemap(b"<urlset>", filtro) == []


def test_m2_url_de_item_solo_http_y_sin_credenciales():
    base = "https://comicbookreadingorders.com/dc/events/x-reading-order/"
    assert url_de_item(base, "javascript:alert(1)") is None
    assert url_de_item(base, "data:text/html,x") is None
    assert url_de_item(base, "mailto:a@b.c") is None
    assert url_de_item(base, "https://user:pass@evil.example/x") is None
    assert url_de_item(base, "https://" + "a" * 600) is None
    assert url_de_item(base, "https://www.dcuniverseinfinite.com/x") == (
        "https://www.dcuniverseinfinite.com/x")
    assert url_de_item(base, "//www.marvel.com/unlimited") == "https://www.marvel.com/unlimited"


def test_m3_url_del_sitio_rechaza_userinfo_puertos_y_paginas_no_validas():
    ro = ReadingOrdersExtractor(CacheHttpFalsa())
    assert ro._url_del_sitio(RO_GUIA)
    assert not ro._url_del_sitio(
        "https://user:pass@comicbookreadingorders.com/dc/events/x-reading-order/")
    assert not ro._url_del_sitio(
        "https://comicbookreadingorders.com:8443/dc/events/x-reading-order/")
    assert not ro._url_del_sitio(
        "https://comicbookreadingorders.com/api/guia")
    assert not ro._url_del_sitio(RO_GUIA + "?x=1")

    cg = ContinuityGuideExtractor(CacheHttpFalsa())
    assert cg._url_del_sitio(CG_GUIA)
    assert not cg._url_del_sitio("https://www.continuityguide.net/")
    assert not cg._url_del_sitio("https://www.continuityguide.net/api/guia")
    assert not cg._url_del_sitio("https://user:pass@www.continuityguide.net/planetx")
    assert not cg._url_del_sitio("https://www.continuityguide.net:8443/planetx")
    assert not cg._url_del_sitio("https://www.continuityguide.net/planetx?format=json")
    assert not cg._url_del_sitio("https://www.continuityguide.net/imagen.jpg")


async def test_m5_entradas_largas_y_enlaces_peligrosos_se_descartan_y_renumeran(fuentes_encendidas):
    html = f"""<html><body><main><h1>Guía</h1><ol class="issues">
      <li class="issue"><div class="issue-main"><span class="issue-title">X-Men #1</span></div>
        <a class="read-link" href="javascript:alert(1)">Read</a></li>
      <li class="issue"><div class="issue-main"><span class="issue-title">X-Men #2</span></div>
        <a class="read-link" href="data:text/html,x">Read</a></li>
      <li class="issue"><div class="issue-main"><span class="issue-title">{'A' * (MAX_REFERENCIA + 10)}</span></div></li>
      <li class="issue"><div class="issue-main"><span class="issue-title">X-Men #3</span></div>
        <a class="read-link" href="//www.marvel.com/unlimited">Read</a></li>
    </ol></main></body></html>"""
    mundo = Mundo({"crisis-on-infinite-earths": html.encode()})
    reloj, cache = Reloj(), CacheHttpFalsa()
    extractor = _extractor(ReadingOrdersExtractor, mundo, cache, reloj)
    async with extractor:
        guia = await extractor.leer_guia(RO_GUIA)
    assert guia is not None
    assert [e.referencia for e in guia.entradas] == ["X-Men #1", "X-Men #2", "X-Men #3"]
    assert [e.orden for e in guia.entradas] == [1, 2, 3]      # renumerado contiguo
    assert guia.entradas[0].item_url is None and guia.entradas[1].item_url is None
    assert guia.entradas[2].item_url == "https://www.marvel.com/unlimited"
    assert guia.titulo is not None and len(guia.titulo) <= 500


def test_validacion_comun_de_url_no_acepta_esquemas_ni_recursos():
    hosts = ("www.continuityguide.net",)
    assert url_de_sitio_valida("https://www.continuityguide.net/planetx", hosts)
    assert not url_de_sitio_valida("http://www.continuityguide.net/planetx", hosts)
    assert not url_de_sitio_valida("https://www.continuityguide.net/x.jpg", hosts)
    assert not url_de_sitio_valida("https://www.continuityguide.net/../x", hosts)


def test_c1_porcentaje_codificado_no_esquiva_la_validacion():
    """SecOps c-1: `%2e%2e` (y doble codificación) equivale a `..` para el servidor."""
    ro = ReadingOrdersExtractor(CacheHttpFalsa())
    assert not ro._url_del_sitio(
        "https://comicbookreadingorders.com/dc/events/x%2e%2e/y/")
    assert not ro._url_del_sitio(
        "https://comicbookreadingorders.com/dc/events/%2e%2e/%2e%2e/etc")
    assert not ro._url_del_sitio(
        "https://comicbookreadingorders.com/dc/events/x%252e%252e/y/")
    assert not ro._url_del_sitio("https://comicbookreadingorders.com/%61pi/guia")

    cg = ContinuityGuideExtractor(CacheHttpFalsa())
    assert not cg._url_del_sitio("https://www.continuityguide.net/%2e%2e/x")
    assert not cg._url_del_sitio("https://www.continuityguide.net/%61pi/guia")
    assert cg._url_del_sitio("https://www.continuityguide.net/planetx")


def test_anio_con_parentesis_se_normaliza_y_el_resolver_lo_entiende():
    """La web escribe el año como `(1982)`; no debe convertirse en `((1982))` (fallo visto en vivo)."""
    extractor = ReadingOrdersExtractor(cache=None)  # type: ignore[arg-type]
    html = (b'<html><body><main><h1>Guia de prueba</h1><ol class="issues">'
            b'<li class="issue"><div class="issue-main"><span class="issue-title">'
            b'New Teen Titans #21</span> <span class="year">(1982)</span></div></li>'
            b'</ol></main></body></html>')
    guia = extractor._parsear(html, RO_GUIA)
    assert guia is not None
    referencia = guia.entradas[0].referencia
    assert referencia == "New Teen Titans #21 (1982)"
    assert parsear_referencia(referencia) is not None
