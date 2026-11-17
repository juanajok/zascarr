"""BL-D3 (#154): lista de mejoras y guardado del perfil de calidad."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.upgrades import MejoraPendiente, PaginaMejoras, ResultadoEscaneo


def _db():
    async def _get():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    return _get


def _cliente():
    app.dependency_overrides[get_db] = _db()
    app.dependency_overrides[require_legal_acknowledgment] = lambda: None
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_legal_acknowledgment, None)


def _fila():
    serie = SimpleNamespace(id=uuid4(), title="Batman")
    issue = SimpleNamespace(id=uuid4(), issue_number="1")
    propuesta = SimpleNamespace(
        id=uuid4(), current_tier=1, candidate_tier=3,
        candidate_title="Batman 001 (Digital).cbz", candidate_indexer="idx",
        candidate_size_bytes=20_000_000, candidate_seeders=5,
        candidate_url="magnet:?xt=1", status="pendiente")
    return MejoraPendiente(propuesta, issue, serie)


def _pagina(filas):
    return PaginaMejoras(filas, len(filas), 1, 1)


def test_lista_de_mejoras_y_estado_vacio():
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.listar_mejoras",
                   AsyncMock(return_value=_pagina([_fila()]))), \
             patch("zascarr.web.mejoras.historial_mejoras", AsyncMock(return_value=[])):
            r = c.get("/ui/mejoras")
        with patch("zascarr.web.mejoras.listar_mejoras",
                   AsyncMock(return_value=_pagina([]))), \
             patch("zascarr.web.mejoras.historial_mejoras", AsyncMock(return_value=[])):
            vacia = c.get("/ui/mejoras")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Batman 001 (Digital)" in r.text and "Descargar esta edición" in r.text
    assert "Tu edición: básica · propuesta: alta" in r.text
    assert vacia.status_code == 200 and "No hay mejoras pendientes" in vacia.text


def test_historial_reciente_muestra_estado():
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.listar_mejoras",
                   AsyncMock(return_value=_pagina([]))), \
             patch("zascarr.web.mejoras.historial_mejoras",
                   AsyncMock(return_value=[_fila()])):
            r = c.get("/ui/mejoras")
    finally:
        _cerrar()
    assert r.status_code == 200 and "Historial reciente (1)" in r.text


def test_escanear_ahora_cuenta_lo_revisado():
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.motivo_sin_escaneo", return_value=None), \
             patch("zascarr.web.mejoras.escanear_mejoras",
                   AsyncMock(return_value=ResultadoEscaneo(3, 2, 0))), \
             patch("zascarr.web.mejoras.listar_mejoras",
                   AsyncMock(return_value=_pagina([]))), \
             patch("zascarr.web.mejoras.historial_mejoras", AsyncMock(return_value=[])):
            r = c.post("/ui/mejoras/escanear")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Revisados 3 números; 2 propuestas nuevas." in r.text


def test_guardar_perfil_de_calidad():
    c = _cliente()
    try:
        with patch("zascarr.web.ajustes.RuntimeSettingsService.save", AsyncMock()):
            r = c.post("/ui/ajustes/guardar/calidad",
                       data={"quality_profile": "mejor",
                             "upgrade_scan_interval_minutes": "1440"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Calidad" in r.text


def test_escanear_sin_prowlarr_explica_el_motivo_sin_json():
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.motivo_sin_escaneo",
                   return_value="Prowlarr no está activo."), \
             patch("zascarr.web.mejoras.listar_mejoras",
                   AsyncMock(return_value=_pagina([]))), \
             patch("zascarr.web.mejoras.historial_mejoras", AsyncMock(return_value=[])):
            r = c.post("/ui/mejoras/escanear")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Prowlarr no está activo." in r.text
    assert "Búsqueda de mejoras terminada" not in r.text


def test_guardar_lote_de_escaneo_valida_y_guarda():
    c = _cliente()
    guardar = AsyncMock()
    try:
        with patch("zascarr.web.ajustes.RuntimeSettingsService.save", guardar):
            r = c.post("/ui/ajustes/guardar/calidad",
                       data={"quality_profile": "equilibrado",
                             "upgrade_scan_interval_minutes": "360",
                             "upgrade_scan_batch": "10"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert guardar.await_args.args[0]["upgrade_scan_batch"] == 10
    # Un valor fuera de la lista segura vuelve a 3, nunca a un número arbitrario.
    guardar.reset_mock()
    c = _cliente()
    try:
        with patch("zascarr.web.ajustes.RuntimeSettingsService.save", guardar):
            c.post("/ui/ajustes/guardar/calidad",
                   data={"upgrade_scan_batch": "9999"})
    finally:
        _cerrar()
    assert guardar.await_args.args[0]["upgrade_scan_batch"] == 3
