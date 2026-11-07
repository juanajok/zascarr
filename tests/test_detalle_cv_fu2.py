"""BL-FU2 PR-3 (#465): Comic Vine, fixture manual y cliente falso. Sin red."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from zascarr.models import MetadataSource
from zascarr.services import comic_vine as modulo_cv
from zascarr.services import discovery as modulo_discovery
from zascarr.services.comic_vine import (
    ComicVineClient,
    CVVolume,
    _parse_cv_volume,
)
from zascarr.services.detalle_edicion import (
    detalle_desde_cv_volumen,
)
from zascarr.services.discovery import DiscoveryResult, DiscoveryService
from zascarr.utils.peticiones import RespuestaNoTransitoria

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = (RAIZ / "docs" / "design" / "fixtures-cobertura"
           / "comicvine_volume_31306.json")


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class _FakeCV:
    def __init__(self, volumen):
        self.get_volume = AsyncMock(return_value=volumen)
        self.get_issue = AsyncMock(return_value=None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


def _resultado():
    return DiscoveryResult(
        source=MetadataSource.COMIC_VINE, external_id="31306", title="Dragon Ball",
        start_year=2003, description=None, cover_url=None, site_url=None)


class TestFixtureYConversion:
    def test_fixture_manual_esta_marcada(self):
        datos = _fixture()
        assert "MANUAL" in datos["_fixture"] and "NO capturada" in datos["_fixture"]

    def test_parsea_volumen_documentado(self):
        volumen = _parse_cv_volume(_fixture())
        assert isinstance(volumen, CVVolume)
        assert volumen.cv_id == 31306 and volumen.name == "Dragon Ball"
        assert volumen.publisher == "Viz"
        assert volumen.start_year == 2003 and volumen.count_of_issues == 16
        assert volumen.first_issue["issue_number"] == "1"
        assert volumen.peticiones == 1

    def test_detalle_no_mete_el_recuento_como_numero_de_ejemplar(self):
        detalle = detalle_desde_cv_volumen(_parse_cv_volume(_fixture()))
        assert detalle.fuente is MetadataSource.COMIC_VINE
        assert detalle.editorial == "Viz" and detalle.anio == 2003
        assert detalle.recuento_numeros == 16
        assert detalle.numero_publicacion is None
        assert detalle.formato is None and detalle.pais is None and detalle.idioma is None
        assert {"formato", "pais", "idioma", "numero_publicacion"} <= set(
            detalle.campos_ausentes)


class TestCliente:
    @pytest.mark.asyncio
    async def test_get_volume_usa_pedir_con_cortesia_y_field_list(self, monkeypatch):
        cliente = ComicVineClient()
        cliente._api_key = "clave"
        respuesta = httpx.Response(200, json={"results": _fixture()})
        llamada = AsyncMock(return_value=respuesta)
        monkeypatch.setattr(modulo_cv, "pedir_con_cortesia", llamada)
        async with cliente:
            cliente._client.get = AsyncMock(side_effect=AssertionError("httpx directo"))
            volumen = await cliente.get_volume(31306)
        assert volumen is not None and volumen.publisher == "Viz"
        assert llamada.await_count == 1
        _cliente, metodo, url = llamada.await_args.args[:3]
        datos = llamada.await_args.kwargs["datos"]
        assert metodo == "GET"
        assert url == "https://comicvine.gamespot.com/api/volume/4050-31306/"
        assert datos["format"] == "json"
        assert "publisher" in datos["field_list"]
        assert "count_of_issues" in datos["field_list"]

    @pytest.mark.asyncio
    async def test_sin_clave_no_llama_ni_hace_red(self, monkeypatch):
        cliente = ComicVineClient()
        cliente._api_key = ""
        llamada = AsyncMock(side_effect=AssertionError("no se puede pedir sin clave"))
        monkeypatch.setattr(modulo_cv, "pedir_con_cortesia", llamada)
        with pytest.raises(RuntimeError):
            await cliente.get_volume(31306)
        llamada.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_404_devuelve_none(self, monkeypatch):
        cliente = ComicVineClient()
        cliente._api_key = "clave"
        async def no_existe(*_a, **_k):
            raise RespuestaNoTransitoria(404)
        monkeypatch.setattr(modulo_cv, "pedir_con_cortesia", no_existe)
        async with cliente:
            assert await cliente.get_volume(31306) is None

    @pytest.mark.asyncio
    async def test_get_issue_usa_4000_y_parsea_numero_y_fecha(self, monkeypatch):
        cliente = ComicVineClient()
        cliente._api_key = "clave"
        respuesta = httpx.Response(200, json={"results": {
            "id": 12345, "issue_number": "1", "cover_date": "2003-01-01",
            "volume": {"id": 31306}}})
        llamada = AsyncMock(return_value=respuesta)
        monkeypatch.setattr(modulo_cv, "pedir_con_cortesia", llamada)
        async with cliente:
            issue = await cliente.get_issue(12345)
        assert issue is not None and issue.issue_number == "1"
        assert issue.cover_date == "2003-01-01"
        assert llamada.await_args.args[2].endswith("/issue/4000-12345/")


class TestDiscoveryComicVine:
    @pytest.mark.asyncio
    async def test_con_clave_hace_una_peticion_y_devuelve_ok(self, monkeypatch):
        monkeypatch.setattr(modulo_discovery, "get_settings", lambda: SimpleNamespace(
            comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True,
            gcd_enabled=True, comicvine_api_key="clave"))
        fake = _FakeCV(_parse_cv_volume(_fixture()))
        monkeypatch.setattr(modulo_discovery, "ComicVineClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "ok" and r.estado.capacidad == "detalle"
        assert r.detalle.editorial == "Viz" and r.detalle.recuento_numeros == 16
        fake.get_volume.assert_awaited_once_with(31306)

    @pytest.mark.asyncio
    async def test_404_es_sin_resultados(self, monkeypatch):
        monkeypatch.setattr(modulo_discovery, "get_settings", lambda: SimpleNamespace(
            comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True,
            gcd_enabled=True, comicvine_api_key="clave"))
        fake = _FakeCV(None)
        monkeypatch.setattr(modulo_discovery, "ComicVineClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "sin_resultados"
