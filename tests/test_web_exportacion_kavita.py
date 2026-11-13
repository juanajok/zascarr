"""B20: API y UI de exportación (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.exportacion_kavita import (
    ParcheComicInfoNoDisponibleError,
    ResumenExportacion,
)


def _cliente():
    async def _db():
        yield SimpleNamespace(
            commit=AsyncMock(), rollback=AsyncMock(), get=AsyncMock(return_value=None))
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_api_exporta_y_devuelve_run():
    resumen = ResumenExportacion("run1", "c1", "/media/export/Grapas", 2, 0, 0, 0, 0, 0)
    c = _cliente()
    try:
        with patch("zascarr.api.exportacion.exportar_coleccion", AsyncMock(return_value=resumen)):
            r = c.post(f"/api/export/collections/{uuid4()}", json={"patch_comicinfo": False})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert r.json()["run_id"] == "run1" and r.json()["resumen"]["materializados"] == 2


def test_api_rechaza_parche_fase_2():
    c = _cliente()
    try:
        with patch("zascarr.api.exportacion.exportar_coleccion", AsyncMock(
                side_effect=ParcheComicInfoNoDisponibleError("fase 2"))):
            r = c.post(f"/api/export/collections/{uuid4()}", json={"patch_comicinfo": True})
    finally:
        _cerrar()
    assert r.status_code == 422 and "fase 2" in r.json()["detail"]


def test_ui_muestra_boton_y_resultado():
    from zascarr.services.colecciones import DetalleColeccion
    from zascarr.web import colecciones

    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    resumen = ResumenExportacion("run1", str(cid), "/media/export/Grapas", 1, 0, 0, 0, 0, 0)
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.exportar_coleccion", AsyncMock(return_value=resumen)):
            r = c.post(f"/ui/colecciones/{cid}/exportar",
                       data={"patch_comicinfo": "0", "confirmo": "1"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "Exportación terminada" in r.text
    assert colecciones.POLITICAS


def test_ui_exige_confirmacion_antes_de_exportar():
    from zascarr.services.colecciones import DetalleColeccion

    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    c = _cliente()
    llamada = AsyncMock()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.exportar_coleccion", llamada):
            r = c.post(f"/ui/colecciones/{cid}/exportar", data={"patch_comicinfo": "0"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "Marca la confirmación" in r.text
    llamada.assert_not_awaited()
