# ruff: noqa: E501
"""#150 BL-C3 web: guardar lectura, fragmento y filtro de biblioteca."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ReadingStatus
from zascarr.services.lectura import EstadoLectura, ValoracionInvalidaError
from zascarr.web import series as web_series


def _estado(estado=ReadingStatus.COMPLETED, rating=4, nota="Muy bueno"):
    return EstadoLectura(str(uuid4()), estado, rating, nota, None, None)


def _override():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db


def test_post_sin_js_redirige_y_no_store(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/leido",
                                 data={"estado": "completed", "rating": "4", "nota": "Muy bueno"},
                                 follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"/ui/series/{sid}")
    assert r.headers["cache-control"] == "no-store"


def test_post_htmx_devuelve_control(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/leido",
                                 data={"estado": "completed"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "lectura-control" in r.text and "Leído" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_valoracion_invalida_422(monkeypatch):
    _override()

    async def _marca(*_a, **_k):
        raise ValoracionInvalidaError("La valoración tiene que estar entre 1 y 5.")

    monkeypatch.setattr(web_series, "marcar", _marca)
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/leido",
                                 data={"estado": "reading", "rating": "0"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 422 and "1 y 5" in r.text


def test_filtro_leido_valido_e_invalido():
    from zascarr.web.library import _leer_filtros, _url_pagina
    filtros = _leer_filtros(1, "", "", "", "", "", "tarjetas", "", "leyendo")
    assert filtros.leido == "leyendo"
    assert "leido=leyendo" in _url_pagina(filtros, page=1)
    filtros = _leer_filtros(1, "", "", "", "", "", "tarjetas", "", "otro")
    assert filtros.leido == "" and any("lectura" in a for a in filtros.avisos)


def test_ruta_lectura_compartida_y_control_segmentado(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/lectura",
                                 data={"estado": "reading"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert 'name="estado"' in r.text
    assert "Sin leer" in r.text and "Leyendo" in r.text and "Leído" in r.text
    assert "Guardar mi lectura" not in r.text  # la fila no lleva botón
