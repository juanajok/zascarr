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
    assert scraper._espera_busqueda_s == 30.0


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
