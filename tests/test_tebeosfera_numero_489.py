"""BL-FU4 (#489): detalle de número de Tebeosfera. Sin red."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from zascarr.models import MetadataSource
from zascarr.services import discovery as modulo_discovery
from zascarr.services import tebeosfera as modulo_tebeosfera
from zascarr.services.detalle_edicion import contrastar, detalle_desde_numero
from zascarr.services.discovery import DiscoveryResult, DiscoveryService
from zascarr.services.tebeosfera import TebeosferaClient, TebeosferaNumero, _parse_numero

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = (RAIZ / "docs" / "design" / "fixtures-cobertura"
           / "tebeosfera_numero_bola_de_drac_2017_super_roja_1.html")
SLUG = "bola_de_drac_2017_planeta_comic_-super_roja-_1"


def _html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class TestParserNumero:
    def test_extrae_numero_editorial_fecha_paginas_y_formato(self):
        numero = _parse_numero(_html(), SLUG)
        assert isinstance(numero, TebeosferaNumero)
        assert numero.numero_publicacion == "1" and numero.numero == "1"
        assert numero.editorial == "Grupo Planeta"
        assert numero.sello == "Planeta Cómic"
        assert numero.anio == 2017 and numero.fecha == "21-III-2017"
        assert numero.paginas == 32
        assert "CUADERNO" in numero.formato_fuente
        assert numero.peticiones == 1
        assert numero.url_ficha.endswith(f"/numeros/{SLUG}.html")

    def test_html_roto_o_sin_ficha_devuelve_none(self):
        assert _parse_numero("", SLUG) is None
        assert _parse_numero("<html>404</html>", SLUG) is None


class TestContrasteConNumero:
    def _etiqueta(self, numero):
        return {"identidad_acreditada": True, "editorial": "Planeta Cómic",
                "anio": 2017, "numero": numero, "pais": None, "idioma": None,
                "formato": "single_issue", "campos": {}}

    def test_numero_coincidente_verifica_y_distinto_es_incorrecto(self):
        detalle = detalle_desde_numero(_parse_numero(_html(), SLUG))
        coincide = contrastar(detalle, self._etiqueta("1"), unidad="numero")
        assert coincide.resultado == "coincidencia_verificada"
        difiere = contrastar(detalle, self._etiqueta("2"), unidad="numero")
        assert difiere.resultado == "incorrecto"
        assert "numero_publicacion_discrepante" in difiere.motivos

    def test_sin_numero_sigue_siendo_ambiguo(self):
        detalle = detalle_desde_numero(_parse_numero(_html(), SLUG))
        detalle = type(detalle)(**{**detalle.__dict__, "numero_publicacion": None})
        r = contrastar(detalle, self._etiqueta(None), unidad="numero")
        assert r.resultado == "ambiguo"
        assert "numero_publicacion_ausente" in r.motivos


class TestGetNumero:
    @pytest.mark.asyncio
    async def test_una_peticion_por_pedir_con_cortesia_y_sin_httpx_directo(self, monkeypatch):
        cliente = TebeosferaClient()
        respuesta = httpx.Response(200, text=_html(),
                                    request=httpx.Request("GET", "https://www.tebeosfera.com/x"))
        llamada = AsyncMock(return_value=respuesta)
        monkeypatch.setattr(modulo_tebeosfera, "pedir_con_cortesia", llamada)
        async with cliente:
            cliente._client.get = AsyncMock(side_effect=AssertionError("httpx directo"))
            numero = await cliente.get_numero(SLUG)
        assert numero is not None and numero.numero_publicacion == "1"
        assert llamada.await_count == 1
        assert llamada.await_args.args[2] == (
            f"https://www.tebeosfera.com/numeros/{SLUG}.html")


class _FakeTebeosfera:
    def __init__(self, numero=None):
        self.get_numero = AsyncMock(return_value=numero)
        self.get_collection = AsyncMock(return_value=None)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


class TestDiscoveryNumero:
    @pytest.mark.asyncio
    async def test_detalle_de_usa_get_numero_si_el_resultado_lo_declara(self, monkeypatch):
        monkeypatch.setattr(modulo_discovery, "get_settings", lambda: SimpleNamespace(
            tebeosfera_enabled=True, comicvine_enabled=True, anilist_enabled=True,
            gcd_enabled=True, comicvine_api_key="x"))
        fake = _FakeTebeosfera(_parse_numero(_html(), SLUG))
        monkeypatch.setattr(modulo_discovery, "TebeosferaClient", lambda: fake)
        resultado = DiscoveryResult(
            source=MetadataSource.TEBEOSFERA, external_id=f"numero:{SLUG}",
            title="BOLA DE DRAC", start_year=2017, description=None,
            cover_url=None, site_url=None)
        r = await DiscoveryService(db=MagicMock()).detalle_de(resultado)
        assert r.estado.estado == "ok" and r.estado.capacidad == "detalle"
        assert r.detalle is not None and r.detalle.numero_publicacion == "1"
        fake.get_numero.assert_awaited_once_with(SLUG)
        fake.get_collection.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_sin_slug_de_numero_sigue_por_coleccion(self, monkeypatch):
        monkeypatch.setattr(modulo_discovery, "get_settings", lambda: SimpleNamespace(
            tebeosfera_enabled=True, comicvine_enabled=True, anilist_enabled=True,
            gcd_enabled=True, comicvine_api_key="x"))
        fake = _FakeTebeosfera(None)
        monkeypatch.setattr(modulo_discovery, "TebeosferaClient", lambda: fake)
        resultado = DiscoveryResult(
            source=MetadataSource.TEBEOSFERA, external_id="thorgal_1990_norma",
            title="Thorgal", start_year=1990, description=None,
            cover_url=None, site_url=None)
        r = await DiscoveryService(db=MagicMock()).detalle_de(resultado)
        assert r.estado.estado == "sin_resultados"
        fake.get_collection.assert_awaited_once_with("thorgal_1990_norma")
