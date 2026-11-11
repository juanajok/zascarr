"""Metron y Open Library: clientes con transporte simulado (sin red real)."""
from __future__ import annotations

import httpx
import pytest

from zascarr.services.metron import ATRIBUCION, MetronClient
from zascarr.services.open_library import OpenLibraryClient
from zascarr.utils.cortesia import PoliticaFuente


@pytest.fixture(autouse=True)
def _fuentes_encendidas(monkeypatch):
    """Los clientes se prueban encendidos; el apagado lo decide DiscoveryService."""
    from types import SimpleNamespace

    from zascarr.services import metron, open_library

    cfg = SimpleNamespace(
        metron_enabled=True, metron_token="", metron_rate_limit=0.0,
        open_library_enabled=True, open_library_rate_limit=0.0,
        open_library_base_url="https://openlibrary.org")
    monkeypatch.setattr("zascarr.config.get_settings", lambda: cfg)
    monkeypatch.setattr(metron, "get_settings", lambda: cfg)
    monkeypatch.setattr(open_library, "get_settings", lambda: cfg)


def _politica(fuente: str) -> PoliticaFuente:
    return PoliticaFuente(fuente, fuente, 0.0, 1, 1)


@pytest.mark.asyncio
async def test_metron_busca_series_con_token_y_sin_portada():
    visto = {}

    def responder(request: httpx.Request) -> httpx.Response:
        visto["auth"] = request.headers.get("authorization")
        visto["url"] = str(request.url)
        return httpx.Response(200, json={"count": 1, "next": None, "results": [{
            "id": 42, "series": "Amazing Spider-Man (1963)", "year_began": 1963,
            "year_end": None, "volume": 1, "issue_count": 900,
            "publisher": {"id": 1, "name": "Marvel"},
            "series_type": {"id": 1, "name": "Single Issue"}, "language": "en",
        }]})

    async with MetronClient(token="tok", politica=_politica("metron"),
                            transporte=httpx.MockTransport(responder)) as cliente:
        hits = await cliente.search_series("spider", limit=5)
    assert visto["auth"] == "Bearer tok"
    assert "q=spider" in visto["url"]
    assert len(hits) == 1
    h = hits[0]
    assert h.metron_id == 42 and h.name.startswith("Amazing Spider-Man")
    assert h.publisher == "Marvel" and h.tradition_guess == "american"
    assert "metron.cloud/series/42" in h.site_url
    assert ATRIBUCION == "Datos de Metron, CC BY-SA 4.0"


@pytest.mark.asyncio
async def test_metron_sin_token_no_hace_red():
    cliente = MetronClient(token="", politica=_politica("metron"))
    assert cliente.configurado is False
    with pytest.raises(RuntimeError):
        async with cliente:
            await cliente.search_series("x")


@pytest.mark.asyncio
async def test_open_library_busca_obras_por_titulo_y_mapea_portada():
    visto = {}

    def responder(request: httpx.Request) -> httpx.Response:
        visto["url"] = str(request.url)
        visto["ua"] = request.headers.get("user-agent")
        return httpx.Response(200, json={"num_found": 1, "docs": [{
            "key": "/works/OL123W", "title": "Blueberry", "first_publish_year": 1963,
            "author_name": ["Jean-Michel Charlier"], "cover_i": 99,
            "publisher": ["Norma"], "language": ["spa"],
        }]})

    async with OpenLibraryClient(politica=_politica("open_library"),
                                transporte=httpx.MockTransport(responder)) as cliente:
        hits = await cliente.search_works("Blueberry", limit=5)
    assert "search.json" in visto["url"] and "fields=" in visto["url"]
    assert visto["ua"].startswith("ZascArr/")
    h = hits[0]
    assert h.work_id == "OL123W" and h.title == "Blueberry"
    assert h.cover_url == "https://covers.openlibrary.org/b/id/99-M.jpg"
    assert h.site_url == "https://openlibrary.org/works/OL123W"


@pytest.mark.asyncio
async def test_open_library_descarta_docs_sin_obra_valida():
    def responder(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"docs": [{"title": "sin clave"}, {"key": "/books/X"}]})

    async with OpenLibraryClient(politica=_politica("open_library"),
                                transporte=httpx.MockTransport(responder)) as cliente:
        assert await cliente.search_works("x", limit=5) == []
