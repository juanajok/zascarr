"""BL-INF4 (#590): rutas de la vista previa del número (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.web import series as web


def _cliente(serie_id: UUID, *, previa):
    class _Sesion:
        async def get(self, _modelo, _id):
            return SimpleNamespace(series_id=serie_id)

    async def _db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_fragmento_devuelve_la_miniatura(tmp_path):
    serie, issue = uuid4(), uuid4()
    jpg = tmp_path / "previa.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xd9")
    c = _cliente(serie, previa=jpg)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=jpg)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa")
    finally:
        _cerrar()

    assert r.status_code == 200
    assert f"/ui/series/{serie}/numero/{issue}/previa.jpg" in r.text
    assert 'class="previa-numero-img"' in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_fragmento_sin_portada_queda_vacio():
    serie, issue = uuid4(), uuid4()
    c = _cliente(serie, previa=None)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa")
    finally:
        _cerrar()

    assert r.status_code == 200 and r.text == ""


def test_imagen_sirve_jpeg_con_etag_y_cache(tmp_path):
    serie, issue = uuid4(), uuid4()
    jpg = tmp_path / "previa.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xd9")
    c = _cliente(serie, previa=jpg)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=jpg)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg")
            r304 = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg",
                         headers={"If-None-Match": r.headers["ETag"]})
    finally:
        _cerrar()

    assert r.status_code == 200 and r.headers["content-type"].startswith("image/jpeg")
    assert r.headers["Cache-Control"] == "private, max-age=86400"
    assert r.headers["ETag"]
    assert r304.status_code == 304


def test_imagen_sin_portada_da_404_sin_cache():
    serie, issue = uuid4(), uuid4()
    c = _cliente(serie, previa=None)
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg")
    finally:
        _cerrar()

    assert r.status_code == 404
    assert r.headers["Cache-Control"] == "no-store"


def test_un_numero_de_otra_serie_da_404():
    serie, issue = uuid4(), uuid4()
    c = _cliente(uuid4(), previa=None)  # la sesión devuelve otra serie
    try:
        with patch.object(web, "ruta_previa", AsyncMock(return_value=None)):
            r = c.get(f"/ui/series/{serie}/numero/{issue}/previa.jpg")
    finally:
        _cerrar()

    assert r.status_code == 404
