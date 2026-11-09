"""#129 C: C1/C2 y no-store, sin red."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.retirar_asociacion import (
    ResultadoRetirarAsociacion,
    VistaPreviaRetirar,
)
from zascarr.web import asociar_fuente as web


class _FakeSession:
    def __init__(self, serie):
        self._serie = serie

    async def execute(self, _s):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=self._serie)
        return r


def _serie():
    return SimpleNamespace(id=uuid4(), title="The Wicked + The Divine", start_year=2014,
                           comic_vine_id=1, anilist_id=None, tebeosfera_slug=None,
                           gcd_id=123, metadata_={}, locked_fields=[],
                           metadata_source="comic_vine")


def _settings():
    return SimpleNamespace(secret_key="x" * 32, comicvine_enabled=True,
                           anilist_enabled=True, tebeosfera_enabled=True,
                           gcd_enabled=True, comicvine_api_key="clave")


class _Servicio:
    def __init__(self, previa=None, resultado=None):
        self.previa = previa
        self.resultado = resultado

    def __call__(self, *_a, **_k):
        return self

    async def previsualizar(self, _sid, _fuente):
        return self.previa

    async def confirmar(self, _token):
        return self.resultado


def _override(serie):
    async def _db():
        yield _FakeSession(serie)
    app.dependency_overrides[get_db] = _db


def test_c1_muestra_garantia_y_no_store(monkeypatch):
    serie = _serie()
    previa = VistaPreviaRetirar(
        str(serie.id), serie.title, "gcd", "123", 2014, "2026-11-09",
        "registrada", "ok", "Vas a quitar la ficha.", "token")
    servicio = _Servicio(previa=previa)
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "RetirarAsociacionDeFuente", servicio)
    _override(serie)
    try:
        r = TestClient(app).get(f"/ui/series/{serie.id}/asociar/gcd/retirar")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Retirar la asociación" in r.text
    assert "La serie, sus números y tus archivos siguen igual. Queda en el historial." in r.text
    assert 'name="token"' in r.text
    assert r.headers["cache-control"] == "no-store"


def test_c2_resultado_retirada(monkeypatch):
    serie = _serie()
    resultado = ResultadoRetirarAsociacion(
        version=1, tipo="retirar_asociacion", operacion_id=str(uuid4()),
        series_id=str(serie.id), resultado="retirada", motivo=None,
        mensaje="retirada", fuente="gcd", id_externo="123")
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "RetirarAsociacionDeFuente", _Servicio(resultado=resultado))
    _override(serie)
    try:
        r = TestClient(app).post(f"/ui/series/{serie.id}/asociar/retirar/confirmar",
                                 data={"token": "x" * 10})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Asociación retirada" in r.text
    assert "No se ha cambiado nada" not in r.text
    assert r.headers["cache-control"] == "no-store"
