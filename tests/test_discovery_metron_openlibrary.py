"""Metron y Open Library dentro de DiscoveryService (sin red)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zascarr.models import MetadataSource
from zascarr.services.discovery import (
    FUENTE_CONFIGURACION_INCOMPLETA,
    FUENTE_OK,
    DiscoveryService,
)
from zascarr.services.metron import MetronResult
from zascarr.services.open_library import OpenLibraryResult


class _DB:
    async def execute(self, _s):
        raise AssertionError("estas pruebas no consultan la BD")


def _ctx(metodo: str, valor):
    cliente = AsyncMock()
    cliente.__aenter__.return_value = cliente
    setattr(cliente, metodo, AsyncMock(return_value=valor))
    return MagicMock(return_value=cliente)


def _ajustes(**extra):
    base = dict(comicvine_enabled=False, anilist_enabled=False, tebeosfera_enabled=False,
                gcd_enabled=False, metron_enabled=True, metron_token="tok",
                open_library_enabled=True)
    base.update(extra)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_metron_y_open_library_se_fusionan_con_su_identidad(monkeypatch):
    monkeypatch.setattr("zascarr.services.discovery.get_settings", lambda: _ajustes())
    metron = [MetronResult(metron_id=42, name="Batman (2011)", year_began=2011,
                           publisher="DC", language="en")]
    openlib = [OpenLibraryResult(work_id="OL123W", title="Blueberry", start_year=1963,
                                 cover_url="https://covers.openlibrary.org/b/id/9-M.jpg",
                                 site_url="https://openlibrary.org/works/OL123W")]
    with patch("zascarr.services.discovery.MetronClient", _ctx("search_series", metron)), \
         patch("zascarr.services.discovery.OpenLibraryClient", _ctx("search_works", openlib)):
        b = await DiscoveryService(_DB()).search_detallada("batman")
    assert {r.source for r in b.resultados} == {MetadataSource.METRON,
                                                MetadataSource.OPEN_LIBRARY}
    assert b.fuentes[MetadataSource.METRON.value] == FUENTE_OK
    assert b.fuentes[MetadataSource.OPEN_LIBRARY.value] == FUENTE_OK
    por_fuente = {r.source: r for r in b.resultados}
    assert por_fuente[MetadataSource.METRON].external_id == "42"
    assert por_fuente[MetadataSource.METRON].cover_url is None
    assert por_fuente[MetadataSource.METRON].editorial == "DC"
    assert por_fuente[MetadataSource.OPEN_LIBRARY].external_id == "OL123W"
    assert por_fuente[MetadataSource.OPEN_LIBRARY].cover_url.startswith("https://covers.")
    assert por_fuente[MetadataSource.OPEN_LIBRARY].site_url.endswith("/OL123W")


@pytest.mark.asyncio
async def test_metron_encendido_sin_token_es_configuracion_incompleta_sin_red(monkeypatch):
    monkeypatch.setattr("zascarr.services.discovery.get_settings",
                        lambda: _ajustes(metron_token=""))
    with patch("zascarr.services.discovery.MetronClient") as cliente:
        b = await DiscoveryService(_DB()).search_detallada("batman")
    assert b.fuentes[MetadataSource.METRON.value] == FUENTE_CONFIGURACION_INCOMPLETA
    cliente.assert_not_called()
