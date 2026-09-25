"""
tests/test_web_ajustes.py

Suite de /ui/ajustes (D11): contrato HTTP de guardar y probar conexión.
Las rutas de "probar" nunca hablan con servicios reales en un test —
httpx se mockea para no depender de red.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app


class FakeSession:
    def __init__(self):
        self._row = MagicMock(values={})
        self.added: list = [self._row]

    async def execute(self, _statement):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self._row)
        return result

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def _override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


@pytest.fixture
def restaurar_settings():
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    originales = {campo: getattr(s, campo) for campo in _ALL_FIELDS}
    yield
    for campo, valor in originales.items():
        setattr(s, campo, valor)


class TestIndex:

    def test_pagina_responde_200_con_las_cuatro_integraciones(self):
        client = TestClient(app)
        r = client.get("/ui/ajustes")
        assert r.status_code == 200
        for nombre in ("Comic Vine", "Prowlarr", "Transmission", "aMule"):
            assert nombre in r.text


class TestGuardar:

    def test_guardar_prowlarr_aplica_al_instante(self, restaurar_settings):
        app.dependency_overrides[get_db] = _override_get_db(FakeSession())
        try:
            client = TestClient(app)
            r = client.post("/ui/ajustes/guardar/prowlarr", data={
                "prowlarr_url": "http://prowlarr-test:9696",
                "prowlarr_api_key": "clave-test",
                "prowlarr_enabled": "true",
            })
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 200
        assert "guardado" in r.text.lower()
        assert get_settings().prowlarr_url == "http://prowlarr-test:9696"
        assert get_settings().prowlarr_enabled is True


class TestProbar:

    def test_comic_vine_sin_clave_falla_sin_llamar_a_la_red(self):
        client = TestClient(app)
        r = client.post("/ui/ajustes/probar/comic-vine", data={"comicvine_api_key": ""})
        assert "✗" in r.text
        assert "Falta la clave" in r.text

    def test_comic_vine_conexion_correcta(self):
        respuesta = MagicMock(status_code=200)
        respuesta.json.return_value = {"error": "OK"}
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=respuesta)):
            client = TestClient(app)
            r = client.post("/ui/ajustes/probar/comic-vine", data={"comicvine_api_key": "clave-valida"})
        assert "✓" in r.text
        assert "Conexión correcta" in r.text

    def test_prowlarr_clave_rechazada(self):
        respuesta = MagicMock(status_code=401)
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=respuesta)):
            client = TestClient(app)
            r = client.post("/ui/ajustes/probar/prowlarr", data={
                "prowlarr_url": "http://x:9696", "prowlarr_api_key": "mala",
            })
        assert "✗" in r.text
        assert "rechazada" in r.text

    def test_conexion_rechazada_sugiere_ufw_y_bind_del_servicio(self):
        """Bug real, reportado: Prowlarr/Transmission/aMule fallaban con
        "no se pudo conectar" sin pista, mientras Comic Vine (host externo)
        funcionaba. Primera hipótesis (bind en 127.0.0.1) descartada con
        datos reales del usuario (ss -tlnp mostraba 0.0.0.0); causa real
        confirmada: ufw con reglas "solo LAN" que no incluyen la subred
        del puente de Docker. La pista cubre ambas causas."""
        import httpx as httpx_module
        with patch("httpx.AsyncClient.get", AsyncMock(side_effect=httpx_module.ConnectError("refused"))):
            client = TestClient(app)
            r = client.post("/ui/ajustes/probar/prowlarr", data={
                "prowlarr_url": "http://host.docker.internal:9696", "prowlarr_api_key": "clave",
            })
        assert "✗" in r.text
        assert "ufw" in r.text
        assert "0.0.0.0" in r.text
        assert "ss -tlnp" in r.text

    def test_error_http_normal_no_lleva_la_pista_de_bind(self):
        """Un 401/500 real significa que SÍ se llegó al servicio — la
        pista de "revisa el bind" solo confundiría ahí."""
        respuesta = MagicMock(status_code=500)
        with patch("httpx.AsyncClient.get", AsyncMock(return_value=respuesta)):
            client = TestClient(app)
            r = client.post("/ui/ajustes/probar/prowlarr", data={
                "prowlarr_url": "http://x:9696", "prowlarr_api_key": "clave",
            })
        assert "✗" in r.text
        assert "0.0.0.0" not in r.text
