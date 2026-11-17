"""CCM: adaptadores de AniList, Metron, Open Library y Fandom (sin red)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from zascarr.core.consolidacion.tipos import EstadoFetch
from zascarr.services.consolidacion.adaptadores import (
    AdaptadorAniList,
    AdaptadorFandom,
    AdaptadorMetron,
    AdaptadorOpenLibrary,
)


class _AniList:
    async def get_manga(self, _id):
        return SimpleNamespace(
            anilist_id=7, title_romaji="Shingeki no Kyojin",
            title_english="Attack on Titan", description="Titanes.",
            start_year=2009, chapters=139, volumes=34, site_url="https://anilist.co/7")


class _Metron:
    async def get_series(self, _id):
        return SimpleNamespace(
            metron_id=9, name="Dylan Dog", year_began=1986, year_ended=None,
            issue_count=400, publisher="Sergio Bonelli", language="it",
            descripcion="Historias de terror.", site_url="https://metron.cloud/9")


class _OpenLibrary:
    async def get_work(self, _id):
        return SimpleNamespace(
            work_id="OL1W", title="AIDP", start_year=2004,
            editorial="Grupo Norma", idioma="es", description="Una obra.",
            site_url="https://openlibrary.org/works/OL1W")


class _Fandom:
    async def get_volume(self, _title, incluir_portada=True):
        return SimpleNamespace(
            page_title="Batman Vol 1", title="Batman", start_year=1940,
            end_year=2011, total_issues=713, kind="comic book",
            description="El caballero oscuro.", cover_url=None, story_arcs=[])


@pytest.mark.asyncio
async def test_anilist_metron_openlibrary_fandom_normalizan_lo_declarado():
    anilist = await AdaptadorAniList(_AniList()).fetch_serie("7")
    assert anilist.estado is EstadoFetch.OK
    assert anilist.ficha.normalizado["edition_scope"]["start_year"] == 2009
    assert anilist.ficha.normalizado["work_scope"]["description"] == "Titanes."

    metron = await AdaptadorMetron(_Metron()).fetch_serie("9")
    assert metron.ficha.normalizado["edition_scope"]["publisher_name"] == "Sergio Bonelli"
    assert metron.ficha.normalizado["edition_scope"]["language"] == "it"

    ol = await AdaptadorOpenLibrary(_OpenLibrary()).fetch_serie("OL1W")
    assert ol.ficha.normalizado["edition_scope"]["publisher_name"] == "Grupo Norma"
    assert ol.ficha.normalizado["edition_scope"]["language"] == "es"

    fandom = await AdaptadorFandom(_Fandom(), "fandom_dc").fetch_serie("Batman Vol 1")
    assert fandom.ficha.normalizado["edition_scope"]["total_issues"] == 713
    assert fandom.ficha.normalizado["work_scope"]["description"] == "El caballero oscuro."


class _CM:
    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *_a):
        return None


@pytest.mark.asyncio
async def test_abrir_adaptadores_incluye_las_ocho_fuentes(monkeypatch):
    from types import SimpleNamespace

    import zascarr.services.consolidacion.adaptadores as mod

    for nombre in ("AniListClient", "MetronClient", "OpenLibraryClient",
                   "ComicVineClient", "TebeosferaClient", "GCDClient"):
        monkeypatch.setattr(mod, nombre, _CM)
    monkeypatch.setattr(mod, "FandomClient", _CM)
    monkeypatch.setattr(
        "zascarr.utils.cache_http.CacheHttp", lambda *_a, **_k: object())
    ajustes = SimpleNamespace(
        comicvine_enabled=True, comicvine_api_key="k",
        tebeosfera_enabled=True, gcd_enabled=True, anilist_enabled=True,
        metron_enabled=True, metron_token="t", open_library_enabled=True,
        fandom_dc_enabled=True, fandom_marvel_enabled=True,
    )
    abierto = await mod.abrir_adaptadores(ajustes)
    try:
        assert set(abierto["adaptadores"]) == {
            "comic_vine", "tebeosfera", "gcd", "anilist", "metron",
            "open_library", "fandom_dc", "fandom_marvel",
        }
    finally:
        await abierto["pila"].aclose()
