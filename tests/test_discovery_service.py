"""
tests/test_discovery_service.py

Suite de DiscoveryService (C0): buscar series en fuentes externas y darlas
de alta. Cierra el círculo vicioso confirmado en producción — Wishlist y
el matcher solo trabajan contra `Series` ya existentes; sin este servicio,
una instalación nueva (tabla `series` vacía) no tiene con qué comparar.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.anilist import AniListResult
from zascarr.services.comic_vine import CVResult
from zascarr.services.discovery import DiscoveryService
from zascarr.services.tebeosfera import TebeosferaResult


class FakeSession:
    def __init__(self, existing: Series | None = None):
        self._existing = existing
        self.added: list = []
        self.queries = 0

    async def execute(self, _statement):
        self.queries += 1
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self._existing)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


def _client_ctx(return_value):
    """AsyncMock que simula `async with XClient() as client: ...`."""
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.search_series = AsyncMock(return_value=return_value)
    client.search_manga = AsyncMock(return_value=return_value)
    return MagicMock(return_value=client)


class TestSearch:

    @pytest.mark.asyncio
    async def test_query_vacia_no_busca_nada(self):
        service = DiscoveryService(db=FakeSession())
        assert await service.search("   ") == []

    @pytest.mark.asyncio
    async def test_fusiona_resultados_de_las_tres_fuentes(self, monkeypatch):
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(comicvine_api_key="una-key"),
        )
        cv = [CVResult(cv_id=1, name="Batman", start_year=2011)]
        anilist = [AniListResult(anilist_id=2, title_romaji="Naruto")]
        tebeo = [TebeosferaResult(slug="thorgal_1981", title="Thorgal", kind="saga")]

        with patch("zascarr.services.discovery.ComicVineClient", _client_ctx(cv)), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx(anilist)), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx(tebeo)):
            service = DiscoveryService(db=FakeSession())
            resultados = await service.search("algo")

        fuentes = {r.source for r in resultados}
        assert fuentes == {MetadataSource.COMIC_VINE, MetadataSource.ANILIST, MetadataSource.TEBEOSFERA}
        assert len(resultados) == 3

    @pytest.mark.asyncio
    async def test_sin_api_key_de_comic_vine_no_lo_intenta(self, monkeypatch):
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(comicvine_api_key=""),
        )
        cv_client = _client_ctx([CVResult(cv_id=1, name="Batman")])
        with patch("zascarr.services.discovery.ComicVineClient", cv_client), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx([])), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx([])):
            service = DiscoveryService(db=FakeSession())
            resultados = await service.search("algo")

        assert resultados == []
        cv_client.return_value.search_series.assert_not_called()

    @pytest.mark.asyncio
    async def test_un_fallo_de_fuente_no_tumba_la_busqueda(self, monkeypatch):
        """Bug real que se evita a propósito: Tebeosfera caído/lento no debe
        impedir ver los resultados de AniList/Comic Vine."""
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(comicvine_api_key=""),
        )
        anilist = [AniListResult(anilist_id=2, title_romaji="Naruto")]
        tebeo_roto = AsyncMock()
        tebeo_roto.__aenter__.side_effect = RuntimeError("tebeosfera caída")

        with patch("zascarr.services.discovery.AniListClient", _client_ctx(anilist)), \
             patch("zascarr.services.discovery.TebeosferaClient", MagicMock(return_value=tebeo_roto)):
            service = DiscoveryService(db=FakeSession())
            resultados = await service.search("algo")

        assert len(resultados) == 1
        assert resultados[0].source == MetadataSource.ANILIST


class TestGetOrCreateSeries:

    @pytest.mark.asyncio
    async def test_crea_serie_nueva(self):
        session = FakeSession(existing=None)
        service = DiscoveryService(db=session)

        series, creada = await service.get_or_create_series(
            source=MetadataSource.COMIC_VINE, external_id="1234",
            title="Batman", tradition=ComicTradition.AMERICAN,
            start_year=2011, cover_url="https://example.com/x.jpg",
        )

        assert creada is True
        assert series.comic_vine_id == 1234
        assert series.title == "Batman"
        assert series.metadata_source == "comic_vine"
        assert session.added == [series]

    @pytest.mark.asyncio
    async def test_id_externo_ya_registrado_no_duplica(self):
        """Bug que se evita a propósito: buscar dos veces la misma serie
        (o volver a encontrarla ya importada) nunca debe violar el UNIQUE
        de comic_vine_id/anilist_id/tebeosfera_slug."""
        existente = Series(id=uuid4(), title="Batman", comic_vine_id=1234)
        session = FakeSession(existing=existente)
        service = DiscoveryService(db=session)

        series, creada = await service.get_or_create_series(
            source=MetadataSource.COMIC_VINE, external_id="1234",
            title="Batman", tradition=ComicTradition.AMERICAN,
        )

        assert creada is False
        assert series is existente
        assert session.added == []

    @pytest.mark.asyncio
    async def test_tebeosfera_usa_slug_como_texto_no_como_entero(self):
        session = FakeSession(existing=None)
        service = DiscoveryService(db=session)

        series, _ = await service.get_or_create_series(
            source=MetadataSource.TEBEOSFERA, external_id="thorgal_1981_distrinovel",
            title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
        )

        assert series.tebeosfera_slug == "thorgal_1981_distrinovel"
        assert series.comic_vine_id is None
        assert series.anilist_id is None

    @pytest.mark.asyncio
    async def test_fuente_desconocida_lanza_value_error(self):
        service = DiscoveryService(db=FakeSession())
        with pytest.raises(ValueError, match="desconocida"):
            await service.get_or_create_series(
                source="algo-raro", external_id="1",
                title="X", tradition=ComicTradition.OTHER,
            )
