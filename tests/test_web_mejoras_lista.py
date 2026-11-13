"""BL-D3 (#154): lista de mejoras y guardado del perfil de calidad."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.upgrades import MejoraPendiente


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
        candidate_url="magnet:?xt=1")
    return MejoraPendiente(propuesta, issue, serie)


def test_lista_de_mejoras_y_estado_vacio():
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.listar_mejoras",
                   AsyncMock(return_value=[_fila()])):
            r = c.get("/ui/mejoras")
        with patch("zascarr.web.mejoras.listar_mejoras", AsyncMock(return_value=[])):
            vacia = c.get("/ui/mejoras")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Batman 001 (Digital)" in r.text and "Descargar esta edición" in r.text
    assert "Tu edición: básica · propuesta: alta" in r.text
    assert vacia.status_code == 200 and "No hay mejoras pendientes" in vacia.text


def test_escanear_ahora_redirige():
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.escanear_mejoras", AsyncMock(return_value=2)):
            r = c.post("/ui/mejoras/escanear", follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and "guardado=escaneado" in r.headers["location"]


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
