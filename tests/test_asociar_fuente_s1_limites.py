# ruff: noqa: E501
"""QA S1: las cotas del token de asociación y la validación ANTES de firmar."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_a import (
    _DB,
    FakeSession,
    _busqueda,
    _resultado,
    _serie,
    _web_client,
)
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import MetadataSource
from zascarr.services import asociar_fuente as servicio
from zascarr.services import tokens_revision as t


def _token_crudo(serie, *, entidad="serie", kind="collection", id_externo="123",
                 titulo="Dragon Ball", anio=2006, sitio_url=None):
    return t.crear_token(t.PROPOSITO_ASOCIAR, str(serie.id), {
        "version": 1, "entidad": entidad, "kind": kind, "fuente": "gcd",
        "id_externo": id_externo, "titulo": titulo, "anio": anio,
        "sitio_url": sitio_url, "huella": "f" * 64,
        "operacion": str(uuid4()), "serie_id": str(serie.id),
    }, "x" * 32)


def _fake_comparar(monkeypatch, resultados):
    class _Fake:
        def __init__(self, _db):
            pass

        async def buscar_en(self, fuente, _q, limit=10):
            return _busqueda(resultados, fuente=fuente)
    monkeypatch.setattr(servicio, "DiscoveryService", _Fake)
    monkeypatch.setattr(servicio, "get_settings", lambda: SimpleNamespace(secret_key="x" * 32))


class TestCotasReales:
    def test_el_maximo_es_el_peor_token_real_y_verifica(self):
        ch = "\U0001F600"
        url = "http://e.co/" + ch * (t.MAX_SITIO_URL - len("http://e.co/"))
        caso = t.AsociacionFirmada(
            1, "serie", "collection", "tebeosfera", ch * t.MAX_ID_ASOCIACION,
            ch * t.MAX_TITULO, t.ANIO_MAX_ASOCIACION, url, "f" * 64,
            "00000000-0000-4000-8000-000000000000",
            "00000000-0000-4000-8000-000000000000")
        token = t.crear_token_asociacion(caso, "x" * 32)
        assert len(token) == t.MAX_TOKEN_ASOCIACION
        assert t.verificar_token_asociacion(token, "x" * 32) is not None
        assert t.MAX_TOKEN_ASOCIACION > 2925

    @pytest.mark.parametrize("id_externo", ["001", "+1", " 1", "0", str(2**63), "１２３", "a/b"])
    def test_ids_no_canonicos_no_verifican(self, id_externo):
        token = _token_crudo(_serie(), id_externo=id_externo)
        assert t.verificar_token_asociacion(token, "x" * 32) is None

    @pytest.mark.parametrize("entidad,kind", [("issue", "collection"), ("serie", "tomo")])
    def test_entidad_y_kind_desconocidos_no_verifican(self, entidad, kind):
        token = _token_crudo(_serie(), entidad=entidad, kind=kind)
        assert t.verificar_token_asociacion(token, "x" * 32) is None

    def test_ausente_invalido_y_caducado(self):
        assert t.verificar_token_asociacion("", "x" * 32) is None
        assert t.verificar_token_asociacion("no-es-un-token", "x" * 32) is None
        serie = _serie()
        token = _token_crudo(serie)
        assert t.verificar_token_asociacion(token, "x" * 32) is not None
        assert t.verificar_token_asociacion(token, "x" * 32, ahora=10**10) is None


class TestNormalizacionAntesDeFirmar:
    def test_sitio_url_larga_se_omite_y_se_firma_null(self, monkeypatch):
        _fake_comparar(monkeypatch, [_resultado(site_url="https://x.example/" + "a" * 600)])
        comp = __import__("asyncio").run(servicio.comparar(_DB(_serie()), uuid4(), MetadataSource.GCD))
        c = comp.candidatas[0]
        assert c.token is not None
        assert t.verificar_token_asociacion(c.token, "x" * 32).sitio_url is None

    @pytest.mark.parametrize("titulo,anio", [("x" * 501, 2006), ("", 2006), ("Dragon Ball", 40000)])
    def test_titulo_o_anio_no_firmables_no_emiten_token(self, monkeypatch, titulo, anio):
        _fake_comparar(monkeypatch, [_resultado(title=titulo, start_year=anio)])
        comp = __import__("asyncio").run(servicio.comparar(_DB(_serie()), uuid4(), MetadataSource.GCD))
        c = comp.candidatas[0]
        assert c.token is None and c.seleccionable is False

    def test_sustituto_unicode_no_lanza_500_ni_firma(self, monkeypatch):
        _fake_comparar(monkeypatch, [_resultado(title="Dragon \ud800 Ball")])
        comp = __import__("asyncio").run(servicio.comparar(_DB(_serie()), uuid4(), MetadataSource.GCD))
        assert comp.candidatas[0].token is None

    @pytest.mark.parametrize("fuente", [MetadataSource.GCD, MetadataSource.COMIC_VINE,
                                         MetadataSource.ANILIST, MetadataSource.TEBEOSFERA])
    def test_saga_de_cualquier_fuente_no_emite_token(self, monkeypatch, fuente):
        _fake_comparar(monkeypatch, [_resultado(kind="saga")])
        comp = __import__("asyncio").run(servicio.comparar(_DB(_serie()), uuid4(), fuente))
        assert comp.candidatas[0].seleccionable is False
        assert comp.candidatas[0].token is None

    def test_id_no_canonico_no_emite_token(self, monkeypatch):
        _fake_comparar(monkeypatch, [_resultado(external_id="001")])
        comp = __import__("asyncio").run(servicio.comparar(_DB(_serie()), uuid4(), MetadataSource.GCD))
        assert comp.candidatas[0].token is None and comp.candidatas[0].seleccionable is False


class TestPreview400:
    def teardown_method(self):
        app.dependency_overrides.pop(get_db, None)

    def test_token_invalido_400_lleva_no_store(self, monkeypatch):
        monkeypatch.setattr("zascarr.web.asociar_fuente.get_settings", lambda: SimpleNamespace(
            secret_key="x" * 32, comicvine_enabled=True, anilist_enabled=True,
            tebeosfera_enabled=True, gcd_enabled=True, comicvine_api_key="clave"))
        serie = _serie()
        r = _web_client(FakeSession(serie)).post(
            f"/ui/series/{serie.id}/asociar/previsualizar", data={"token": "x" * 10})
        assert r.status_code == 400
        assert r.headers["cache-control"] == "no-store"
