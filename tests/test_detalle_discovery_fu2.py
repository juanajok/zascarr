"""BL-FU2 PR-2 (#465): detalle en Discovery + GCD. Sin red ni BD."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from zascarr.models import MetadataSource
from zascarr.services import discovery as modulo
from zascarr.services import gcd as modulo_gcd
from zascarr.services.detalle_edicion import (
    CAPACIDAD_DETALLE,
    DetalleEdicion,
    detalle_desde_gcd_serie,
)
from zascarr.services.discovery import DiscoveryResult, DiscoveryService
from zascarr.services.estados_fuentes import CAPACIDAD_BUSQUEDA, ESTADOS_DE_FUENTE
from zascarr.services.gcd import GCDClient, GCDSerie
from zascarr.services.tebeosfera import TebeosferaColeccion
from zascarr.utils.cortesia import CortesiaEnEspera
from zascarr.utils.peticiones import ReintentosAgotados


def _settings(**extra):
    base = dict(comicvine_enabled=True, anilist_enabled=True, tebeosfera_enabled=True,
                gcd_enabled=True, comicvine_api_key="clave")
    base.update(extra)
    return SimpleNamespace(**base)


def _resultado(fuente=MetadataSource.GCD, external_id="1"):
    return DiscoveryResult(
        source=fuente, external_id=external_id, title="Thorgal", start_year=1990,
        description=None, cover_url=None, site_url=None)


def _coleccion():
    return TebeosferaColeccion(
        slug="thorgal_1990_norma", editorial="Norma Editorial", sello=None,
        anio=1990, anio_fin=None, numeracion_inicio=1, numeracion_fin=20,
        numeracion_texto="1 a 20", formato_fuente="CUADERNO / GRAPA",
        pais="ES", peticiones=1)


class _FakeTebeosfera:
    def __init__(self, coleccion=None):
        self.coleccion = coleccion
        self.get_collection = AsyncMock(return_value=coleccion)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


class _FakeGCD:
    def __init__(self, serie=None, editorial=None):
        self.get_series = AsyncMock(return_value=serie)
        self.get_publisher = AsyncMock(return_value=editorial)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


def _serie(**extra):
    base = dict(gcd_id=1, name="Thorgal", year_began=1990, year_ended=1995,
                publisher="https://www.comics.org/api/publisher/2/",
                language="Spanish", country="Spain", publishing_format="comic book",
                binding="saddle-stitched")
    base.update(extra)
    return GCDSerie(**base)


class TestCapacidadDetalle:
    def test_capacidad_detalle_no_altera_el_vocabulario_de_133(self):
        assert CAPACIDAD_DETALLE == "detalle"
        assert CAPACIDAD_BUSQUEDA == "busqueda"
        assert CAPACIDAD_DETALLE != CAPACIDAD_BUSQUEDA
        assert {
            "ok", "sin_resultados", "fallo_transitorio", "configuracion_incompleta",
            "limite_de_cortesia", "fuente_apagada"} == ESTADOS_DE_FUENTE
        assert modulo.CAPACIDAD_DETALLE == CAPACIDAD_DETALLE


class TestDetalleDe:
    @pytest.mark.asyncio
    async def test_tebeosfera_ok_y_sin_resultados(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        fake = _FakeTebeosfera(_coleccion())
        monkeypatch.setattr(modulo, "TebeosferaClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(
            _resultado(MetadataSource.TEBEOSFERA, "thorgal_1990_norma"))
        assert r.estado.estado == "ok" and r.estado.capacidad == CAPACIDAD_DETALLE
        assert r.detalle is not None and r.detalle.editorial == "Norma Editorial"

        fake_vacia = _FakeTebeosfera(None)
        monkeypatch.setattr(modulo, "TebeosferaClient", lambda: fake_vacia)
        r2 = await DiscoveryService(db=MagicMock()).detalle_de(
            _resultado(MetadataSource.TEBEOSFERA, "no_existe"))
        assert r2.estado.estado == "sin_resultados" and r2.detalle is None

    @pytest.mark.asyncio
    async def test_gcd_sin_raw_usa_get_series_y_get_publisher(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        fake = _FakeGCD(_serie(), editorial="Panini España")
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "ok" and r.estado.capacidad == CAPACIDAD_DETALLE
        assert r.detalle is not None
        assert r.detalle.editorial == "Panini España"
        assert r.detalle.peticiones == 2
        fake.get_series.assert_awaited_once_with(1)
        fake.get_publisher.assert_awaited_once_with("https://www.comics.org/api/publisher/2/")

    @pytest.mark.asyncio
    async def test_gcd_con_raw_resuelve_la_editorial_sin_pedir_la_serie(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        fake = _FakeGCD(_serie(), editorial="Panini España")
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        resultado = _resultado()
        resultado.raw = {"name": "Thorgal", "year_began": 1990,
                         "publisher": "https://www.comics.org/api/publisher/2/",
                         "language": "Spanish", "country": "Spain",
                         "publishing_format": "comic book"}
        r = await DiscoveryService(db=MagicMock()).detalle_de(resultado)
        assert r.estado.estado == "ok" and r.detalle is not None
        assert r.detalle.editorial == "Panini España"
        assert r.detalle.peticiones == 1
        fake.get_series.assert_not_awaited()
        fake.get_publisher.assert_awaited_once_with(
            "https://www.comics.org/api/publisher/2/")

    @pytest.mark.asyncio
    async def test_gcd_con_raw_y_nombre_ya_presente_no_pide_nada(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        fake = _FakeGCD(_serie())
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        resultado = _resultado()
        resultado.raw = {"name": "Thorgal", "year_began": 1990,
                         "publisher_name": "Panini España",
                         "language": "Spanish", "country": "Spain"}
        r = await DiscoveryService(db=MagicMock()).detalle_de(resultado)
        assert r.detalle is not None and r.detalle.editorial == "Panini España"
        assert r.detalle.peticiones == 0
        fake.get_series.assert_not_awaited()
        fake.get_publisher.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_gcd_publisher_que_falla_deja_editorial_ausente(self, monkeypatch):
        from zascarr.services.detalle_edicion import contrastar
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        fake = _FakeGCD(_serie())
        fake.get_publisher = AsyncMock(side_effect=RuntimeError("red"))
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        resultado = _resultado()
        resultado.raw = {"name": "Thorgal", "year_began": 1990,
                         "publisher": "https://www.comics.org/api/publisher/2/",
                         "language": "Spanish", "country": "Spain"}
        r = await DiscoveryService(db=MagicMock()).detalle_de(resultado)
        assert r.estado.estado == "ok" and r.detalle is not None
        assert r.detalle.editorial is None
        assert "editorial" in r.detalle.campos_ausentes
        assert r.detalle.peticiones == 1
        etiqueta = {"identidad_acreditada": True, "editorial": "Panini España",
                    "anio": 1990, "numero": None, "pais": "ES", "idioma": "es",
                    "formato": "single_issue", "campos": {}}
        assert contrastar(r.detalle, etiqueta, unidad="serie").resultado == "ambiguo"

    @pytest.mark.asyncio
    async def test_gcd_sin_serie_es_sin_resultados(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        fake = _FakeGCD(None)
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "sin_resultados"

    @pytest.mark.asyncio
    async def test_cv_sin_clave_es_configuracion_incompleta_sin_red(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings(comicvine_api_key=""))
        r = await DiscoveryService(db=MagicMock()).detalle_de(
            _resultado(MetadataSource.COMIC_VINE, "1"))
        assert r.estado.estado == "configuracion_incompleta"

    @pytest.mark.asyncio
    async def test_anilist_sin_metodo_autorizado(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())
        r = await DiscoveryService(db=MagicMock()).detalle_de(
            _resultado(MetadataSource.ANILIST, "1"))
        assert r.estado.estado == "sin_metodo_autorizado"

    @pytest.mark.asyncio
    async def test_fuente_apagada_no_consulta(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings",
                            lambda: _settings(gcd_enabled=False))
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "fuente_apagada"

    @pytest.mark.asyncio
    async def test_cortesia_y_429_son_limite(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())

        async def espera(*_a, **_k):
            raise CortesiaEnEspera("gcd", "comics.org", 12.0, "cortesia")
        fake = _FakeGCD()
        fake.get_series = espera
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "limite_de_cortesia"
        assert r.estado.reintentar_en == 12

        async def agotado(*_a, **_k):
            raise ReintentosAgotados("gcd", 3, 429)
        fake2 = _FakeGCD()
        fake2.get_series = agotado
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake2)
        r2 = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r2.estado.estado == "limite_de_cortesia"

    @pytest.mark.asyncio
    async def test_error_de_red_es_fallo_transitorio(self, monkeypatch):
        monkeypatch.setattr(modulo, "get_settings", lambda: _settings())

        async def roto(*_a, **_k):
            raise RuntimeError("red")
        fake = _FakeGCD()
        fake.get_series = roto
        monkeypatch.setattr(modulo, "GCDClient", lambda: fake)
        r = await DiscoveryService(db=MagicMock()).detalle_de(_resultado())
        assert r.estado.estado == "fallo_transitorio"


class TestGCDCliente:
    @pytest.mark.asyncio
    async def test_get_series_y_publisher_por_pedir_con_cortesia(self, monkeypatch):
        cliente = GCDClient()
        serie = {"name": "Thorgal", "year_began": 1990, "publisher":
                 "https://www.comics.org/api/publisher/2/", "language": "Spanish",
                 "country": "Spain", "publishing_format": "comic book",
                 "binding": "saddle-stitched", "issue_count": None,
                 "active_issues": [], "issue_descriptors": []}
        respuestas = [httpx.Response(200, json=serie), httpx.Response(200, json={"name": "Panini"})]
        llamadas = []

        async def pedir(_cliente, metodo, url, **_kwargs):
            llamadas.append((metodo, url))
            return respuestas.pop(0)
        monkeypatch.setattr(modulo_gcd, "pedir_con_cortesia", pedir)
        async with cliente:
            cliente._client.get = AsyncMock(side_effect=AssertionError("httpx directo"))
            s = await cliente.get_series(1)
            editorial = await cliente.get_publisher(s.publisher)
        assert s is not None and s.name == "Thorgal" and s.year_began == 1990
        assert editorial == "Panini"
        assert llamadas == [
            ("GET", "https://www.comics.org/api/series/1/"),
            ("GET", "https://www.comics.org/api/publisher/2/"),
        ]

    @pytest.mark.asyncio
    async def test_publisher_de_otro_origen_no_se_pide(self):
        cliente = GCDClient()
        async with cliente:
            assert await cliente.get_publisher("https://ejemplo.invalid/api/publisher/2/") is None


def test_detalle_desde_gcd_serie_no_inventa_numero_ni_editorial():
    detalle = detalle_desde_gcd_serie(_serie(), editorial=None, peticiones=1)
    assert isinstance(detalle, DetalleEdicion)
    assert detalle.editorial is None
    assert detalle.numero_publicacion is None
    assert detalle.pais == "ES" and detalle.idioma == "es"
    assert "editorial" in detalle.campos_ausentes
    assert "numero_publicacion" in detalle.campos_ausentes


def test_coste_del_detalle_gcd_con_raw_url_o_nombre():
    """El banco presupuesta 1 petición si el raw trae URL; 0 si ya trae el nombre (#516)."""
    from scripts.medicion import banco_cobertura as banco
    from zascarr.services.gcd import GCDResult

    con_url = GCDResult(gcd_id=1, name="Thorgal", raw={
        "name": "Thorgal", "publisher": "https://www.comics.org/api/publisher/2/"})
    con_nombre = GCDResult(gcd_id=1, name="Thorgal", raw={
        "name": "Thorgal", "publisher_name": "Panini España"})
    sin_publisher = GCDResult(gcd_id=1, name="Thorgal", raw={"name": "Thorgal"})
    assert banco._coste_detalle("gcd", con_url) == 1
    assert banco._coste_detalle("gcd", con_nombre) == 0
    assert banco._coste_detalle("gcd", sin_publisher) == 0
