"""BL-D3 (#154): propuesta UI y confirmación de descarga."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.calidad import (
    ArchivoActual,
    Calidad,
    MejoraCandidata,
    ResultadoMejoras,
)
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.orchestrator import crear_token_candidato
from zascarr.services.prowlarr import SearchResult


def _contexto():
    serie = SimpleNamespace(id=uuid4(), title="Batman")
    issue = SimpleNamespace(id=uuid4(), issue_number="1")
    ficha = SimpleNamespace(serie=serie, issue=issue, archivos=[SimpleNamespace()])
    return serie, issue, ficha


def _cliente(ficha):
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[require_legal_acknowledgment] = lambda: None
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_legal_acknowledgment, None)


def test_busqueda_muestra_tu_edicion_y_candidato_mejor():
    serie, issue, ficha = _contexto()
    candidato = SearchResult("Batman 001 (Digital).cbz", "idx",
                             "magnet:?xt=mejor", 20_000_000, 5, "comics")
    resultado = ResultadoMejoras(
        True, None,
        [ArchivoActual("batman-001.cbz", Calidad(1, "básica", "1200 px"))],
        [MejoraCandidata(candidato, Calidad(3, "alta", "digital"))])
    c = _cliente(ficha)
    try:
        with patch("zascarr.web.series.cargar_ficha_numero", AsyncMock(return_value=ficha)), \
             patch("zascarr.web.series.buscar_mejoras", AsyncMock(return_value=resultado)):
            r = c.post(f"/ui/series/{serie.id}/numero/{issue.id}/mejorar")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Tu edición" in r.text and "Batman 001 (Digital)" in r.text
    assert "Descargar esta edición" in r.text


def test_confirmar_descarga_envia_el_candidato():
    serie, issue, ficha = _contexto()
    candidato = SearchResult("Batman 001 (Digital).cbz", "idx",
                             "magnet:?xt=mejor", 20_000_000, 5, "comics")
    secret = "secreto-de-prueba"
    token = crear_token_candidato(issue.id, candidato, secret)
    c = _cliente(ficha)
    try:
        with patch("zascarr.web.series.cargar_ficha_numero", AsyncMock(return_value=ficha)), \
             patch("zascarr.web.series.get_settings",
                   return_value=SimpleNamespace(secret_key=secret)), \
             patch("zascarr.web.series.Orchestrator.enviar_candidato_de_mejora",
                   AsyncMock(return_value=(
                       True, "Descarga enviada. Cuando llegue, el importador la añadirá."))):
            r = c.post(f"/ui/series/{serie.id}/numero/{issue.id}/mejorar/descargar",
                       data={"token": token})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Descarga enviada" in r.text
