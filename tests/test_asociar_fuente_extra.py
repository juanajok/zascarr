"""Asociar otra fuente: Metron, Open Library y Fandom en el flujo (#1006)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from zascarr.models import ComicTradition, MetadataSource
from zascarr.services import discovery as mod
from zascarr.services.asociacion_fuente import _valor
from zascarr.services.asociar_fuente import tiene_identidad
from zascarr.services.discovery import DiscoveryService
from zascarr.web import asociar_fuente as web


def test_tiene_identidad_acepta_las_cuatro_fuentes_nuevas():
    for campo, valor in (
        ("metron_id", 9), ("open_library_id", "OL1W"),
        ("fandom_dc_slug", "Batman_Vol_1"), ("fandom_marvel_slug", "Avengers_Vol_1"),
    ):
        assert tiene_identidad(SimpleNamespace(**{campo: valor})) is True


def test_valor_textual_para_open_library_y_fandom():
    assert _valor("tebeosfera", "slug") == "slug"
    assert _valor("open_library", "OL1W") == "OL1W"
    assert _valor("fandom_dc", "Batman_Vol_1") == "Batman_Vol_1"
    assert _valor("metron", "9") == 9


class _Fandom:
    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return None

    async def search_series(self, _q, limit=10):
        return ["Batman Vol 1", "Batman Vol 2"]

    async def get_volume(self, page, incluir_portada=True):
        return SimpleNamespace(title=page, start_year=1940, end_year=2011,
                               total_issues=713, kind="comic book",
                               description="El caballero oscuro.", cover_url=None,
                               story_arcs=[])


@pytest.mark.asyncio
async def test_busqueda_fandom_devuelve_slug_firmable(monkeypatch):
    monkeypatch.setattr(mod, "FandomClient", _Fandom)
    resultados = await DiscoveryService(db=None)._search_fandom(
        MetadataSource.FANDOM_DC, "Batman", 2)
    assert [r.external_id for r in resultados] == ["Batman_Vol_1", "Batman_Vol_2"]
    assert resultados[0].source is MetadataSource.FANDOM_DC
    assert resultados[0].tradition_guess is ComicTradition.AMERICAN


def test_el_selector_ofrece_las_ocho_fuentes(monkeypatch):
    ajustes = SimpleNamespace(
        comicvine_enabled=True, comicvine_api_key="k", anilist_enabled=True,
        tebeosfera_enabled=True, gcd_enabled=True, metron_enabled=True,
        metron_token="t", open_library_enabled=True,
        fandom_dc_enabled=True, fandom_marvel_enabled=True,
    )
    monkeypatch.setattr(web, "get_settings", lambda: ajustes)
    opciones = {o["clave"] for o in web._opciones()}
    assert {"metron", "open_library", "fandom_dc", "fandom_marvel"} <= opciones
