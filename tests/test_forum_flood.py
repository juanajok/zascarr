"""SCR4 — Search Flood Control de IPB: espera compartida, nunca «sin resultados» (sin red)."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from zascarr.models import WishlistStatus
from zascarr.services.forum_scraper import (
    ForumFloodControl,
    ForumScraper,
    detectar_flood,
)
from zascarr.services.orchestrator import (
    MOTIVO_FORO_ESPERA,
    MOTIVO_SIN_RESULTADOS,
    Orchestrator,
)
from zascarr.utils.cortesia import CortesiaEnEspera, CortesiaProceso

FIXTURES = Path(__file__).parent / "fixtures" / "foro"
BASE = "http://foro.example/forum"
ENCENDIDO = SimpleNamespace(forum_enabled=True, forum_url=BASE, forum_username="lector",
                            forum_password="clave", forum_rate_limit=2.0,
                            forum_search_rate_limit=25.0, prowlarr_enabled=False)


@pytest.fixture(autouse=True)
def _foro_encendido(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: ENCENDIDO)


class Reloj:
    def __init__(self):
        self.t = 1000.0
        self.dormidos: list[float] = []

    def __call__(self) -> float:
        return self.t

    async def dormir(self, segundos: float) -> None:
        self.dormidos.append(segundos)
        self.t += segundos


def _scraper(handler, *, reloj=None):
    reloj = reloj or Reloj()
    return ForumScraper(
        BASE, rate_limit=0,
        crear_cliente=lambda: httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=False),
        cortesia=CortesiaProceso(reloj=reloj, dormir=reloj.dormir),
        reloj=reloj, dormir=reloj.dormir, espera_max_s=300.0)


def _html(nombre: str) -> httpx.Response:
    return httpx.Response(200, content=(FIXTURES / nombre).read_bytes(),
                          headers={"content-type": "text/html; charset=utf-8"})


def _una_busqueda(respuesta):
    peticiones: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        peticiones.append(request)
        return respuesta

    return _scraper(handler), peticiones


def _orquestador() -> Orchestrator:
    db = SimpleNamespace(flush=AsyncMock())
    return Orchestrator(db=db)


# ── AC-FLD-1: detector inglés y español, con la caja de error de IPB ──────────────────────

@pytest.mark.parametrize(("fixture", "segundos"), [("flood_es.html", 42.0),
                                                  ("flood_en.html", 35.0)])
def test_ac_fld_1_flood_en_ingles_y_espanol_devuelve_los_segundos(fixture, segundos):
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    assert detectar_flood(html) == segundos


def test_la_caja_de_error_y_la_frase_hacen_falta_las_dos():
    frase_sola = "<p>Search flood control: try again in 90 seconds</p>"
    caja_sola = '<div class="errorwrap"><p>No se encontraron resultados.</p></div>'
    assert detectar_flood(frase_sola) is None
    assert detectar_flood(caja_sola) is None
    assert detectar_flood(
        '<div id="errorwrap"><p>Search flood control. Try again in 5 seconds.</p></div>'
    ) == 20.0                                   # recorte inferior
    assert detectar_flood(
        '<div class="errorbox"><p>Flood control: try again in 999 seconds.</p></div>'
    ) == 60.0                                   # recorte superior


# ── AC-FLD-2/3/5: lanza, nunca [] ────────────────────────────────────────────────────────

async def test_ac_fld_2_y_5_use_ipb_search_lanza_y_hace_una_sola_peticion():
    scraper, peticiones = _una_busqueda(_html("flood_es.html"))
    with pytest.raises(ForumFloodControl) as info:
        await scraper.use_ipb_search("Año Uno", abrir_temas=False)
    assert info.value.segundos == 42.0 and info.value.motivo == "flood"
    assert len(peticiones) == 1


async def test_ac_fld_3_cero_resultados_sin_caja_es_una_lista_vacia():
    scraper, _ = _una_busqueda(_html("cero_resultados.html"))
    assert await scraper.use_ipb_search("Año Uno", abrir_temas=False) == []


async def test_ac_fld_4_tras_el_flood_la_siguiente_llamada_espera_sin_red():
    scraper, peticiones = _una_busqueda(_html("flood_es.html"))
    with pytest.raises(ForumFloodControl):
        await scraper.use_ipb_search("Año Uno", abrir_temas=False)
    assert len(peticiones) == 1
    with pytest.raises(CortesiaEnEspera):
        await scraper.use_ipb_search("Año Uno", abrir_temas=False)
    assert len(peticiones) == 1                     # no se ha vuelto a pedir nada


# ── AC-FLD-6: el orquestador distingue espera de vacío ───────────────────────────────────

async def test_ac_fld_6_el_orquestador_deja_espera_y_no_sin_resultados(monkeypatch):
    orq = _orquestador()
    orq._build_query = AsyncMock(return_value="consulta")
    orq._marcar_busqueda = AsyncMock()
    orq._forum_fallback = AsyncMock(
        side_effect=ForumFloodControl("foro.example:80", 30.0))
    item = SimpleNamespace(id=uuid4(), status=None, last_error=None, numero=None,
                           series_id=None)
    monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: ENCENDIDO)

    assert await orq._search_and_rank(item) is None
    assert item.last_error == MOTIVO_FORO_ESPERA != MOTIVO_SIN_RESULTADOS
    assert item.status is WishlistStatus.WANTED
    orq.db.flush.assert_awaited()


async def test_el_forum_fallback_deja_propagar_el_flood(monkeypatch):
    from zascarr.services import forum_scraper as modulo_foro

    class ForoConFlood:
        def __init__(self, **_kw):
            pass

        async def login(self, *_a, **_k):
            raise ForumFloodControl("foro.example:80", 30.0)

        async def use_ipb_search(self, *_a, **_k):      # pragma: no cover - no llega
            raise AssertionError("no se busca si el login ya está en flood")

    monkeypatch.setattr(modulo_foro, "ForumScraper", ForoConFlood)
    monkeypatch.setattr("zascarr.services.orchestrator.get_settings", lambda: ENCENDIDO)
    orq = _orquestador()
    with pytest.raises(ForumFloodControl):
        await orq._forum_fallback("thorgal")
