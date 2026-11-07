"""#489: editorial de colección robusta y número resuelto dentro de la colección."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from zascarr.models import MetadataSource
from zascarr.services import discovery as modulo_discovery
from zascarr.services.discovery import DiscoveryResult, DiscoveryService
from zascarr.services.tebeosfera import (
    TebeosferaClient,
    TebeosferaColeccion,
    TebeosferaNumero,
    _parse_collection,
)

RAIZ = Path(__file__).resolve().parents[1]
FIXTURES = RAIZ / "docs" / "design" / "fixtures-cobertura"


class TestEditorial:
    def test_la_ficha_nueva_lee_editorial_y_sello(self):
        html = (FIXTURES / "tebeosfera_coleccion_thorgal_1990.html").read_text(
            encoding="utf-8")
        coleccion = _parse_collection(html, "thorgal_1990_norma_-subcoleccion-")
        assert coleccion is not None
        assert coleccion.editorial == "Grupo NORMA"
        assert coleccion.sello == "Norma Editorial"
        assert coleccion.anio == 1990 and coleccion.pais == "ES"

    def test_la_ficha_existente_sigue_leyendo_editorial(self):
        html = (FIXTURES / "tebeosfera_coleccion_dragon_ball_1992.html").read_text(
            encoding="utf-8")
        coleccion = _parse_collection(html, "bola_de_drac")
        assert coleccion is not None
        assert coleccion.editorial == "Grupo Planeta"
        assert coleccion.sello == "Planeta DeAgostini"


class TestNumeroDentroDeColeccion:
    def _coleccion(self, slugs):
        return TebeosferaColeccion(slug="coll", editorial="X", numeros_slugs=tuple(slugs))

    @pytest.mark.asyncio
    async def test_encuentra_el_enlace_y_hace_dos_peticiones(self):
        cliente = TebeosferaClient()
        cliente.get_collection = AsyncMock(return_value=self._coleccion(
            ["otra_1", "bola_15", "bola_16"]))
        numero = TebeosferaNumero(slug="bola_15", numero_publicacion="15")
        cliente.get_numero = AsyncMock(return_value=numero)
        resultado = await cliente.get_numero_de_coleccion("coll", 15)
        assert resultado.slug == "bola_15" and resultado.numero_publicacion == "15"
        assert resultado.peticiones == 2
        cliente.get_collection.assert_awaited_once()
        cliente.get_numero.assert_awaited_once_with("bola_15", espera_max_s=30.0)

    @pytest.mark.asyncio
    async def test_sin_enlace_no_pide_numero(self):
        cliente = TebeosferaClient()
        cliente.get_collection = AsyncMock(return_value=self._coleccion(["bola_1"]))
        cliente.get_numero = AsyncMock()
        assert await cliente.get_numero_de_coleccion("coll", 15) is None
        cliente.get_numero.assert_not_awaited()


class _FakeTebeosfera:
    def __init__(self, numero):
        self.get_numero_de_coleccion = AsyncMock(return_value=numero)
        self.get_collection = AsyncMock(return_value=None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


class TestDiscoveryNumeroEsperado:
    @pytest.mark.asyncio
    async def test_detalle_de_usa_numero_esperado_en_coleccion(self, monkeypatch):
        monkeypatch.setattr(modulo_discovery, "get_settings", lambda: SimpleNamespace(
            tebeosfera_enabled=True, comicvine_enabled=True, anilist_enabled=True,
            gcd_enabled=True, comicvine_api_key="x"))
        numero = TebeosferaNumero(slug="bola_15", numero_publicacion="15",
                                  editorial="Grupo Planeta", anio=1992)
        fake = _FakeTebeosfera(numero)
        monkeypatch.setattr(modulo_discovery, "TebeosferaClient", lambda: fake)
        resultado = DiscoveryResult(
            source=MetadataSource.TEBEOSFERA, external_id="coll", title="BOLA",
            start_year=1992, description=None, cover_url=None, site_url=None)
        r = await DiscoveryService(db=MagicMock()).detalle_de(
            resultado, numero_esperado=15)
        assert r.estado.estado == "ok" and r.detalle.numero_publicacion == "15"
        fake.get_numero_de_coleccion.assert_awaited_once_with("coll", 15)
        fake.get_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_numero_esperado_sigue_por_coleccion(self, monkeypatch):
        monkeypatch.setattr(modulo_discovery, "get_settings", lambda: SimpleNamespace(
            tebeosfera_enabled=True, comicvine_enabled=True, anilist_enabled=True,
            gcd_enabled=True, comicvine_api_key="x"))
        fake = _FakeTebeosfera(None)
        monkeypatch.setattr(modulo_discovery, "TebeosferaClient", lambda: fake)
        resultado = DiscoveryResult(
            source=MetadataSource.TEBEOSFERA, external_id="coll", title="BOLA",
            start_year=1992, description=None, cover_url=None, site_url=None)
        await DiscoveryService(db=MagicMock()).detalle_de(resultado)
        fake.get_collection.assert_awaited_once_with("coll")
