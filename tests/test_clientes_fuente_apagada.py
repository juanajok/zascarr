# ruff: noqa: E501
"""AC-15: una fuente apagada no reserva ni envía en NINGÚN cliente (PR-1b).

La excepción explícita es la prueba de Ajustes (`permitir_apagada=True`), cubierta en
`test_clientes_cortesia.py`. Aquí se comprueba que Tebeosfera, GCD y foro no la usan.
"""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from zascarr.services.forum_scraper import ForumScraper
from zascarr.services.gcd import GCDClient
from zascarr.services.tebeosfera import TebeosferaClient
from zascarr.utils.cortesia import FuenteApagada

BASE = "https://foro.example"


def _apagadas(monkeypatch, **encendidas):
    ajustes = dict(comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
                   gcd_enabled=False, forum_enabled=False, forum_url="",
                   comicvine_rate_limit=1.0, anilist_rate_limit=1.5,
                   tebeosfera_rate_limit=2.5, gcd_rate_limit=2.0, forum_rate_limit=2.0)
    ajustes.update(encendidas)
    falsos = SimpleNamespace(**ajustes)
    monkeypatch.setattr("zascarr.config.get_settings", lambda: falsos)
    monkeypatch.setattr("zascarr.services.tebeosfera.get_settings", lambda: falsos)
    monkeypatch.setattr("zascarr.services.gcd.get_settings", lambda: falsos)
    return falsos


def _cliente_sin_red(peticiones):
    def handler(request: httpx.Request):
        peticiones.append(str(request.url))
        return httpx.Response(200, text="<html></html>")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False)


async def test_tebeosfera_apagada_no_envia(monkeypatch):
    _apagadas(monkeypatch)
    peticiones: list[str] = []
    cliente = TebeosferaClient(transporte=httpx.MockTransport(
        lambda r: peticiones.append(str(r.url)) or httpx.Response(200, text="<html></html>")))
    with pytest.raises(FuenteApagada):
        async with cliente:
            await cliente.search_series("Thorgal")
    assert peticiones == []


async def test_gcd_apagada_no_envia(monkeypatch):
    _apagadas(monkeypatch)
    peticiones: list[str] = []
    cliente = GCDClient()
    cliente._client = _cliente_sin_red(peticiones)
    try:
        with pytest.raises(FuenteApagada):
            await cliente.search_series("Batman")
    finally:
        await cliente._client.aclose()
    assert peticiones == []


async def test_foro_apagado_no_envia_ni_en_login_ni_en_busqueda(monkeypatch):
    _apagadas(monkeypatch)
    peticiones: list[str] = []
    scraper = ForumScraper(BASE, rate_limit=0,
                           crear_cliente=lambda: _cliente_sin_red(peticiones))
    with pytest.raises(FuenteApagada):
        await scraper.login("usuario", "clave")
    with pytest.raises(FuenteApagada):
        await scraper._get(f"{BASE}/index.php?showtopic=1")
    assert peticiones == []
