"""Filtro de indexers de Prowlarr desde ZascArr (sin Prowlarr real)."""
from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from zascarr.services import prowlarr as modulo
from zascarr.services.prowlarr import ProwlarrClient


@pytest.fixture(autouse=True)
def _ajustes(monkeypatch):
    cfg = SimpleNamespace(prowlarr_url="http://prowlarr:9696", prowlarr_api_key="clave")
    monkeypatch.setattr(modulo, "get_settings", lambda: cfg)


@pytest.mark.asyncio
async def test_lista_indexers_con_sus_categorias():
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/indexer"
        assert request.headers["x-api-key"] == "clave"
        return httpx.Response(200, json=[
            {"id": 1, "name": "Internet Archive", "enable": True,
             "capabilities": {"categories": [{"name": "Books"}]}},
            {"id": 2, "name": "Apagado", "enable": False, "capabilities": {"categories": []}},
        ])

    indexers = await ProwlarrClient(transporte=httpx.MockTransport(responder)).list_indexers()
    assert [i.name for i in indexers] == ["Internet Archive", "Apagado"]
    assert indexers[0].categories == ["Books"] and indexers[1].enabled is False


@pytest.mark.asyncio
async def test_la_busqueda_envia_indexer_ids_repetidos():
    visto = {}

    def responder(request: httpx.Request) -> httpx.Response:
        visto["url"] = str(request.url)
        return httpx.Response(200, json=[])

    await ProwlarrClient(transporte=httpx.MockTransport(responder)).search(
        "Batman", categories=[7030, 7020], indexer_ids=[3, 7])
    assert "indexerIds=3" in visto["url"] and "indexerIds=7" in visto["url"]
