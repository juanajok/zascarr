"""BL-FU1 (#464): GCD no ofrece ediciones no españolas en el flujo de tebeo español.

Sin red: el helper es puro y los clientes se inyectan con resultados falsos.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zascarr.models import MetadataSource
from zascarr.services.anilist import AniListResult
from zascarr.services.comic_vine import CVResult
from zascarr.services.discovery import DiscoveryService
from zascarr.services.gcd import GCDResult, es_edicion_espanola
from zascarr.services.tebeosfera import TebeosferaResult


class TestHelperPuro:
    def test_pais_es_o_idioma_es_es_edicion_espanola(self):
        assert es_edicion_espanola(GCDResult(gcd_id=1, name="x", country="ES")) is True
        assert es_edicion_espanola(GCDResult(gcd_id=1, name="x", country="es")) is True
        assert es_edicion_espanola(GCDResult(gcd_id=1, name="x", language="es")) is True
        assert es_edicion_espanola(GCDResult(gcd_id=1, name="x", language="Spanish")) is True
        assert es_edicion_espanola(GCDResult(gcd_id=1, name="x", language="ESPAÑOL")) is True
        # Basta uno de los dos datos para conservarla.
        assert es_edicion_espanola(
            GCDResult(gcd_id=1, name="x", country="ES", language="fr")) is True

    def test_pais_o_idioma_extranjero_da_false(self):
        assert es_edicion_espanola(
            GCDResult(gcd_id=1, name="x", country="US", language="en")) is False
        assert es_edicion_espanola(
            GCDResult(gcd_id=1, name="x", country="FR")) is False
        assert es_edicion_espanola(
            GCDResult(gcd_id=1, name="x", language="fr")) is False

    def test_sin_pais_ni_idioma_da_none_no_se_descarta(self):
        assert es_edicion_espanola(GCDResult(gcd_id=1, name="x")) is None
        assert es_edicion_espanola(
            GCDResult(gcd_id=1, name="x", country="", language="")) is None


def _ctx(valor):
    cliente = AsyncMock()
    cliente.__aenter__.return_value = cliente
    cliente.search_series = AsyncMock(return_value=valor)
    cliente.search_manga = AsyncMock(return_value=valor)
    return MagicMock(return_value=cliente)


def _ajustes():
    return SimpleNamespace(
        comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True,
        gcd_enabled=True, comicvine_api_key="clave")


async def _buscar(monkeypatch, gcd):
    monkeypatch.setattr("zascarr.services.discovery.get_settings", lambda: _ajustes())
    with patch("zascarr.services.discovery.ComicVineClient", _ctx([CVResult(cv_id=1, name="x")])), \
         patch("zascarr.services.discovery.AniListClient",
               _ctx([AniListResult(anilist_id=2, title_romaji="x")])), \
         patch("zascarr.services.discovery.TebeosferaClient",
               _ctx([TebeosferaResult(slug="x", title="x", kind="saga")])), \
         patch("zascarr.services.discovery.GCDClient", _ctx(gcd)):
        return await DiscoveryService(db=MagicMock()).search("Thorgal")


@pytest.mark.asyncio
async def test_un_resultado_frances_no_aparece_y_uno_espanol_si(monkeypatch):
    frances = GCDResult(gcd_id=10, name="Les mondes de Thorgal", language="fr", country="FR")
    espanol = GCDResult(gcd_id=11, name="Thorgal", language="es", country="ES")
    resultados, _ = await _buscar(monkeypatch, [frances, espanol])
    gcd = [r for r in resultados if r.source is MetadataSource.GCD]
    assert [r.external_id for r in gcd] == ["11"]
    assert "Les mondes de Thorgal" not in {r.title for r in resultados}
    assert gcd[0].idioma_no_informado is False


@pytest.mark.asyncio
async def test_sin_pais_ni_idioma_se_conserva_y_se_marca(monkeypatch):
    sin_dato = GCDResult(gcd_id=12, name="Thorgal (sin ficha de idioma)")
    resultados, _ = await _buscar(monkeypatch, [sin_dato])
    gcd = [r for r in resultados if r.source is MetadataSource.GCD]
    assert len(gcd) == 1 and gcd[0].idioma_no_informado is True


@pytest.mark.asyncio
async def test_si_todos_los_resultados_son_extranjeros_gcd_queda_sin_candidatos(monkeypatch):
    monkeypatch.setattr("zascarr.services.discovery.get_settings", lambda: _ajustes())
    with patch("zascarr.services.discovery.ComicVineClient", _ctx([])), \
         patch("zascarr.services.discovery.AniListClient", _ctx([])), \
         patch("zascarr.services.discovery.TebeosferaClient", _ctx([])), \
         patch("zascarr.services.discovery.GCDClient",
               _ctx([GCDResult(gcd_id=10, name="Les mondes de Thorgal",
                               language="fr", country="FR")])):
        busqueda = await DiscoveryService(db=MagicMock()).search_detallada("Thorgal")
    assert busqueda.resultados == []
    assert busqueda.fuentes["gcd"] == "sin_resultados"   # #133 no cambia de vocabulario
