"""#155/BL-D6: UI de colecciones (servicio sustituido, sin BD)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.colecciones import (
    ColeccionResumen,
    DetalleColeccion,
    ResultadoColeccion,
    SerieDeColeccion,
)


def _cliente():
    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_lista_muestra_colecciones_y_politica():
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.listar_colecciones", AsyncMock(return_value=[
                ColeccionResumen("c1", "Grapas", "En curso", "incluir", 2)])):
            r = c.get("/ui/colecciones")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Grapas" in r.text and "Buscar faltantes de todas" in r.text
    assert "No buscar automáticamente" in r.text and "(heredar)" not in r.text
    assert "Nueva colección" in r.text


def test_detalle_muestra_series_y_selector():
    c = _cliente()
    detalle = DetalleColeccion("c1", "Grapas", "En curso", "excluir",
                               [SerieDeColeccion(
                                   "s1", "Flash", 1987, "faltantes",
                                   "Buscar los números que faltan", "ninguno",
                                   "No buscar automáticamente")])
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[
                 SerieDeColeccion("s2", "Batman", 1940, "ninguno")])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[
                 {"run_id": "run123456789", "fecha": datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
                  "materializados": 2, "saltados": 0, "errores": 0, "modo": "hardlink"}])):
            cid = uuid4()
            r = c.get(f"/ui/colecciones/{cid}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Flash" in r.text and "Batman" in r.text
    assert "Guardada: Buscar los números que faltan" in r.text
    assert "Efectiva: No buscar automáticamente" in r.text
    assert "No buscar automáticamente" in r.text
    assert "Borrar esta colección" in r.text
    assert "confirm(" not in r.text
    assert ">ninguno<" not in r.text and ">heredar<" not in r.text
    assert 'id="exportaciones"' in r.text and "run123456789" in r.text


def test_crear_valida_y_redirige():
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.crear_coleccion", AsyncMock(
                return_value=ResultadoColeccion(
                    False, {"name": "El nombre no puede estar vacío."}))), \
             patch("zascarr.web.colecciones.listar_colecciones", AsyncMock(return_value=[])):
            r = c.post("/ui/colecciones/nueva", data={"name": "", "description": "",
                                                       "auto_search": "heredar"})
        assert r.status_code == 200 and "El nombre no puede estar vacío." in r.text
        with patch("zascarr.web.colecciones.crear_coleccion", AsyncMock(
                return_value=ResultadoColeccion(True, coleccion=SimpleNamespace(id=uuid4())))):
            r = c.post("/ui/colecciones/nueva", data={"name": "Grapas", "description": "",
                                                       "auto_search": "incluir"},
                       follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].endswith("guardado=creada")
    finally:
        _cerrar()


def test_editar_asignar_quitar_y_borrar_redirigen():
    c = _cliente()
    coleccion = SimpleNamespace(id=uuid4())
    detalle = DetalleColeccion(str(coleccion.id), "Grapas", None, "heredar", [])
    try:
        with patch("zascarr.web.colecciones.editar_coleccion", AsyncMock(
                return_value=ResultadoColeccion(True, coleccion=coleccion))):
            r = c.post(f"/ui/colecciones/{coleccion.id}/editar",
                       data={"name": "Otra", "description": "", "auto_search": "excluir"},
                       follow_redirects=False)
        assert r.status_code == 303 and "guardado=guardada" in r.headers["location"]
        with patch("zascarr.web.colecciones.asignar_serie", AsyncMock(
                return_value=ResultadoColeccion(True, coleccion=coleccion))):
            r = c.post(f"/ui/colecciones/{coleccion.id}/series",
                       data={"serie_id": str(uuid4())}, follow_redirects=False)
        assert r.status_code == 303 and "guardado=asignada" in r.headers["location"]
        with patch("zascarr.web.colecciones.quitar_serie", AsyncMock(return_value=True)):
            r = c.post(f"/ui/colecciones/{coleccion.id}/series/{uuid4()}/quitar",
                       follow_redirects=False)
        assert r.status_code == 303 and "guardado=quitada" in r.headers["location"]
        with patch("zascarr.web.colecciones.borrar_coleccion", AsyncMock(return_value=True)):
            r = c.post(f"/ui/colecciones/{coleccion.id}/borrar", follow_redirects=False)
        assert r.status_code == 303 and "guardado=borrada" in r.headers["location"]
        del detalle
    finally:
        _cerrar()
