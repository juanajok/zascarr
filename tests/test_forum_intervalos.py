"""SCR4 — intervalos separados del foro: lectura 2 s, búsqueda 25 s (sin red)."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from zascarr.config import Settings
from zascarr.services.forum_scraper import ForumScraper
from zascarr.utils.cortesia import CortesiaProceso, politica_de

BASE = "http://foro.example/forum"
VACIA = b"<html><body>No se encontraron resultados.</body></html>"
AJUSTES = SimpleNamespace(forum_enabled=True, forum_url=BASE, forum_username="lector",
                          forum_password="clave", forum_rate_limit=2.0,
                          forum_search_rate_limit=25.0)


class Reloj:
    def __init__(self):
        self.t = 1000.0
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        self.t += segundos


@pytest.fixture(autouse=True)
def _foro_encendido(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: AJUSTES)


def _scraper(reloj, peticiones, **kw):
    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return httpx.Response(200, content=VACIA,
                              headers={"content-type": "text/html; charset=utf-8"})

    return ForumScraper(
        BASE, crear_cliente=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False),
        cortesia=CortesiaProceso(reloj=reloj, dormir=reloj.dormir),
        reloj=reloj, dormir=reloj.dormir, espera_max_s=300.0, **kw)


def test_ac_int_1_la_lectura_sigue_en_dos_segundos():
    ajustes = Settings(_env_file=None)
    assert politica_de("foro", ajustes).intervalo_min_s == 2.0


def test_ac_int_2_y_4_el_constructor_toma_ambas_politicas_de_settings():
    scraper = ForumScraper(BASE)
    assert scraper._politica.intervalo_min_s == 2.0
    assert scraper._politica_busqueda.intervalo_min_s == 25.0
    assert scraper._politica_busqueda.max_intentos == 1
    # 2 × intervalo (POST + redirección de IPB) + margen: 60 s (bug 2026-11-16).
    assert scraper._espera_busqueda_s == 60.0


async def test_ac_int_3_dos_busquedas_seguidas_esperan_veinticinco_segundos():
    reloj = Reloj()
    peticiones: list[httpx.Request] = []
    scraper = _scraper(reloj, peticiones)
    assert await scraper.use_ipb_search("Año Uno", abrir_temas=False) == []
    assert await scraper.use_ipb_search("Batman", abrir_temas=False) == []
    assert len(peticiones) == 2
    assert reloj.dormidos == [25.0]


async def test_la_lectura_no_espera_los_veinticinco_de_la_busqueda():
    reloj = Reloj()
    peticiones: list[httpx.Request] = []
    scraper = _scraper(reloj, peticiones, rate_limit=0)
    assert scraper._politica.intervalo_min_s == 0.0
    assert await scraper.use_ipb_search("Año Uno", abrir_temas=False) == []
    assert reloj.dormidos == []                 # primera petición: no espera


async def test_la_busqueda_tras_redireccion_de_ipb_cabe_en_el_presupuesto():
    """IPB responde 302 al POST de búsqueda: el salto vuelve a esperar el intervalo.

    Con presupuesto de una sola espera (30 s) el salto se rechazaba y el foro no buscaba
    nunca (bug 2026-11-16). Debe completarse con ~2 × intervalo.
    """
    reloj = Reloj()
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        url = str(request.url)
        if "act=Login" in url:
            return httpx.Response(302, headers={
                "location": "/forum/index.php",
                "set-cookie": "member_id=1; Path=/"})
        if "act=Search" in url and request.method == "POST":
            return httpx.Response(302, headers={
                "location": "/forum/index.php?act=Search&CODE=02&searchid=1"})
        if "act=Search" in url:
            return httpx.Response(200, content=VACIA,
                                  headers={"content-type": "text/html; charset=utf-8"})
        return httpx.Response(
            200, content=b"<html><form action='?act=Login&CODE=01&s=S1'></form></html>",
            headers={"content-type": "text/html; charset=utf-8"})

    scraper = ForumScraper(
        BASE, crear_cliente=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False),
        cortesia=CortesiaProceso(reloj=reloj, dormir=reloj.dormir),
        reloj=reloj, dormir=reloj.dormir, espera_max_s=300.0)
    assert await scraper.login("usuario", "clave") is True
    reloj.dormidos.clear()
    assert await scraper.use_ipb_search("DC K.O.", abrir_temas=False) == []
    assert len(peticiones) >= 4                       # entrada + login + POST + GET del 302
    # POST: intervalo de búsqueda (25 s); el 302: ritmo de lectura (2 s), no otra búsqueda.
    assert sum(reloj.dormidos) == pytest.approx(25.0 + 2.0)
