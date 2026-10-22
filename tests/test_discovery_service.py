"""
tests/test_discovery_service.py

Suite de DiscoveryService (C0): buscar series en fuentes externas y darlas
de alta. Cierra el círculo vicioso confirmado en producción — Wishlist y
el matcher solo trabajan contra `Series` ya existentes; sin este servicio,
una instalación nueva (tabla `series` vacía) no tiene con qué comparar.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zascarr.models import MetadataSource, Series
from zascarr.services.anilist import AniListResult
from zascarr.services.comic_vine import CVResult
from zascarr.services.discovery import DiscoveryService, ProcedenciaTradicion
from zascarr.services.gcd import GCDResult
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
        assert await service.search("   ") == ([], [])

    @pytest.mark.asyncio
    async def test_fusiona_resultados_de_las_cuatro_fuentes(self, monkeypatch):
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(comicvine_api_key="una-key"),
        )
        cv = [CVResult(cv_id=1, name="Batman", start_year=2011)]
        anilist = [AniListResult(anilist_id=2, title_romaji="Naruto")]
        tebeo = [TebeosferaResult(slug="thorgal_1981", title="Thorgal", kind="saga")]
        gcd = [GCDResult(gcd_id=3, name="Batman", language="en", country="us")]

        with patch("zascarr.services.discovery.ComicVineClient", _client_ctx(cv)), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx(anilist)), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx(tebeo)), \
             patch("zascarr.services.discovery.GCDClient", _client_ctx(gcd)):
            service = DiscoveryService(db=FakeSession())
            resultados, avisos = await service.search("algo")

        fuentes = {r.source for r in resultados}
        assert fuentes == {
            MetadataSource.COMIC_VINE, MetadataSource.ANILIST,
            MetadataSource.TEBEOSFERA, MetadataSource.GCD,
        }
        assert len(resultados) == 4
        assert avisos == []
        procedencias = {r.source: r.procedencia for r in resultados}
        assert procedencias == {
            MetadataSource.COMIC_VINE: ProcedenciaTradicion.POR_DEFECTO,
            MetadataSource.ANILIST: ProcedenciaTradicion.EXPLICITA,
            MetadataSource.TEBEOSFERA: ProcedenciaTradicion.POR_DEFECTO,
            MetadataSource.GCD: ProcedenciaTradicion.TRANSFORMADA,
        }

    @pytest.mark.asyncio
    async def test_gcd_sin_idioma_ni_pais_no_sugiere_other_ni_inventa_procedencia(
            self, monkeypatch):
        """CA6: si GCD no reconoce el idioma/país no sugiere nada; no se inventa `other`."""
        monkeypatch.setattr("zascarr.services.discovery.get_settings",
                            lambda: MagicMock(comicvine_api_key="una-key"))
        gcd = [GCDResult(gcd_id=3, name="Desconocido", language=None, country=None)]
        with patch("zascarr.services.discovery.ComicVineClient", _client_ctx([])), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx([])), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx([])), \
             patch("zascarr.services.discovery.GCDClient", _client_ctx(gcd)):
            resultados, _ = await DiscoveryService(db=FakeSession()).search("algo")
        (r,) = resultados
        assert r.tradition_guess is None and r.procedencia is None

    @pytest.mark.asyncio
    async def test_sin_api_key_de_comic_vine_avisa_y_no_lo_intenta(self, monkeypatch):
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(comicvine_api_key=""),
        )
        cv_client = _client_ctx([CVResult(cv_id=1, name="Batman")])
        with patch("zascarr.services.discovery.ComicVineClient", cv_client), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx([])), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx([])), \
             patch("zascarr.services.discovery.GCDClient", _client_ctx([])):
            service = DiscoveryService(db=FakeSession())
            resultados, avisos = await service.search("algo")

        assert resultados == []
        cv_client.return_value.search_series.assert_not_called()
        assert any("Comic Vine" in a for a in avisos)

    @pytest.mark.asyncio
    async def test_un_fallo_de_fuente_no_tumba_la_busqueda_y_lo_avisa(self, monkeypatch):
        """Bug real que se evita a propósito: Tebeosfera caído/lento no debe
        impedir ver los resultados de AniList/Comic Vine, pero el
        coleccionista debe enterarse de que Tebeosfera no respondió."""
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(comicvine_api_key=""),
        )
        anilist = [AniListResult(anilist_id=2, title_romaji="Naruto")]
        tebeo_roto = AsyncMock()
        tebeo_roto.__aenter__.side_effect = RuntimeError("tebeosfera caída")

        with patch("zascarr.services.discovery.AniListClient", _client_ctx(anilist)), \
             patch("zascarr.services.discovery.TebeosferaClient",
                   MagicMock(return_value=tebeo_roto)), \
             patch("zascarr.services.discovery.GCDClient", _client_ctx([])):
            service = DiscoveryService(db=FakeSession())
            resultados, avisos = await service.search("algo")

        assert len(resultados) == 1
        assert resultados[0].source == MetadataSource.ANILIST
        assert any("Tebeosfera" in a for a in avisos)

    @pytest.mark.asyncio
    async def test_fuente_desactivada_no_se_consulta_y_las_demas_si(self, monkeypatch):
        """B8: «fuente apagada» vale también en Descubrir — la desactivada no se
        instancia ni consulta; las demás siguen devolviendo resultados."""
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(
                comicvine_api_key="una-key", comicvine_enabled=False,
                anilist_enabled=True, tebeosfera_enabled=True,
            ),
        )
        anilist = [AniListResult(anilist_id=2, title_romaji="Naruto")]
        tebeo = [TebeosferaResult(slug="thorgal_1981", title="Thorgal", kind="saga")]
        cv_client = _client_ctx([CVResult(cv_id=1, name="Batman")])

        with patch("zascarr.services.discovery.ComicVineClient", cv_client), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx(anilist)), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx(tebeo)), \
             patch("zascarr.services.discovery.GCDClient", _client_ctx([])):
            service = DiscoveryService(db=FakeSession())
            resultados, avisos = await service.search("algo")

        # Comic Vine desactivada → su cliente nunca se instancia ni consulta.
        cv_client.return_value.search_series.assert_not_called()
        fuentes = {r.source for r in resultados}
        assert fuentes == {MetadataSource.ANILIST, MetadataSource.TEBEOSFERA}

    @pytest.mark.asyncio
    async def test_gcd_desactivado_no_se_consulta_y_las_demas_si(self, monkeypatch):
        """GCD es «solo Descubrir»: su interruptor también vive en Ajustes y
        apagado significa cero consultas a GCD, con las demás funcionando."""
        monkeypatch.setattr(
            "zascarr.services.discovery.get_settings",
            lambda: MagicMock(
                comicvine_api_key="una-key", comicvine_enabled=True,
                anilist_enabled=True, tebeosfera_enabled=True, gcd_enabled=False,
            ),
        )
        anilist = [AniListResult(anilist_id=2, title_romaji="Naruto")]
        gcd_client = _client_ctx([GCDResult(gcd_id=3, name="Batman")])

        with patch("zascarr.services.discovery.ComicVineClient", _client_ctx([])), \
             patch("zascarr.services.discovery.AniListClient", _client_ctx(anilist)), \
             patch("zascarr.services.discovery.TebeosferaClient", _client_ctx([])), \
             patch("zascarr.services.discovery.GCDClient", gcd_client):
            service = DiscoveryService(db=FakeSession())
            resultados, avisos = await service.search("algo")

        gcd_client.return_value.search_series.assert_not_called()
        assert {r.source for r in resultados} == {MetadataSource.ANILIST}
