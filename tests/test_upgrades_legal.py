"""BL-D3 (#154): hallazgos F-1 y F-2 de SecOps (2026-11-13).

F-1: el escaneo periódico de mejoras busca en Prowlarr por su cuenta; sin aviso legal aceptado
no debe buscar nada (CLAUDE.md §5.2, igual que ya hace el orquestador con la lista de deseados).

F-2: el token de una propuesta no sirve en otra, ni con un enlace distinto del que guarda la fila.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.orchestrator import crear_token_candidato
from zascarr.services.prowlarr import SearchResult
from zascarr.services.upgrades import MejoraPendiente, escanear_mejoras

SECRETO = "secreto-de-prueba-f2"


def _settings():
    return SimpleNamespace(quality_profile="equilibrado", prowlarr_enabled=True,
                           prowlarr_url="http://prowlarr:9696",
                           prowlarr_api_key="clave", upgrade_scan_batch=3)


# ── F-1 ──────────────────────────────────────────────────────────────────────────────────
class _DbQueNoSeToca:
    """Cualquier acceso a la base de datos antes del aviso legal es un fallo."""

    async def execute(self, *a, **k):  # pragma: no cover - solo falla si hay regresión
        raise AssertionError("el escaneo tocó la base de datos sin aviso legal aceptado")

    async def commit(self):  # pragma: no cover
        raise AssertionError("el escaneo confirmó sin aviso legal aceptado")


@pytest.mark.asyncio
async def test_escaneo_periodico_sin_aviso_legal_no_busca_nada():
    """Regresión F-1: `escanear_mejoras` consultaba Prowlarr cada ciclo sin `is_acknowledged`."""
    buscar = AsyncMock()
    with patch("zascarr.services.upgrades.is_acknowledged", AsyncMock(return_value=False)), \
         patch("zascarr.services.upgrades.get_settings", return_value=_settings()), \
         patch("zascarr.services.upgrades.buscar_mejoras", buscar):
        assert await escanear_mejoras(_DbQueNoSeToca()) == 0
    buscar.assert_not_called()


@pytest.mark.asyncio
async def test_escaneo_con_aviso_aceptado_sigue_su_camino():
    """Contraprueba: con el aviso aceptado, el escaneo llega a leer la base de datos."""
    leida = AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: [])))
    db = SimpleNamespace(execute=leida, commit=AsyncMock())
    with patch("zascarr.services.upgrades.is_acknowledged", AsyncMock(return_value=True)), \
         patch("zascarr.services.upgrades.get_settings", return_value=_settings()):
        assert await escanear_mejoras(db) == 0
    leida.assert_awaited()


# ── F-2 ──────────────────────────────────────────────────────────────────────────────────
def _fila(url="magnet:?xt=1"):
    serie = SimpleNamespace(id=uuid4(), title="Batman")
    issue = SimpleNamespace(id=uuid4(), issue_number="1")
    propuesta = SimpleNamespace(
        id=uuid4(), current_tier=1, candidate_tier=3,
        candidate_title="Batman 001 (Digital).cbz", candidate_indexer="idx",
        candidate_size_bytes=20_000_000, candidate_seeders=5, candidate_url=url)
    return MejoraPendiente(propuesta, issue, serie)


def _cliente():
    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[require_legal_acknowledgment] = lambda: None
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(require_legal_acknowledgment, None)


def _candidato(url):
    return SearchResult("Batman 001 (Digital).cbz", "idx", url, 20_000_000, 5, "comics")


def _descargar(fila, token, *, reclamar=None, enviar=None):
    """POST /ui/mejoras/{propuesta}/descargar con todo lo de fuera simulado."""
    reclamar = reclamar or AsyncMock(return_value=fila.propuesta)
    enviar = enviar or AsyncMock(return_value=(True, "ok"))
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.obtener_mejora", AsyncMock(return_value=fila)), \
             patch("zascarr.web.mejoras.listar_mejoras", AsyncMock(return_value=[])), \
             patch("zascarr.web.mejoras.get_settings",
                   return_value=SimpleNamespace(secret_key=SECRETO)), \
             patch("zascarr.web.mejoras.reclamar_mejora", reclamar), \
             patch("zascarr.web.mejoras.marcar_descargada", AsyncMock(return_value=True)), \
             patch("zascarr.web.mejoras.devolver_mejora", AsyncMock(return_value=True)), \
             patch("zascarr.web.mejoras.Orchestrator.enviar_candidato_de_mejora", enviar):
            r = c.post(f"/ui/mejoras/{fila.propuesta.id}/descargar", data={"token": token},
                       follow_redirects=False)
    finally:
        _cerrar()
    return r, reclamar, enviar


def test_el_token_de_una_propuesta_no_sirve_en_otra_del_mismo_numero():
    """Regresión F-2: el token se ligaba al NÚMERO. Tras descartar la propuesta A, la B (mismo
    número, otro enlace) aceptaba el token viejo de A (vale 600 s) y enviaba el enlace de A."""
    a, b = _fila("magnet:?xt=a"), _fila("magnet:?xt=b")
    b = MejoraPendiente(b.propuesta, a.issue, a.serie)          # mismo número
    token_viejo_de_a = crear_token_candidato(a.issue.id, a.candidato, SECRETO)  # como se hacía
    r, reclamar, enviar = _descargar(b, token_viejo_de_a)
    assert r.status_code == 200 and "caducado" in r.text
    reclamar.assert_not_called()
    enviar.assert_not_called()


def test_el_token_de_otra_propuesta_tampoco_sirve():
    a, b = _fila("magnet:?xt=a"), _fila("magnet:?xt=b")
    token_de_a = crear_token_candidato(a.propuesta.id, a.candidato, SECRETO)
    r, reclamar, enviar = _descargar(b, token_de_a)
    assert r.status_code == 200 and "caducado" in r.text
    reclamar.assert_not_called()
    enviar.assert_not_called()


def test_token_con_enlace_distinto_del_que_guarda_la_fila_se_rechaza():
    """Doble ligadura: aunque la firma sea de esta propuesta, el enlace debe ser el de la fila."""
    fila = _fila("magnet:?xt=bueno")
    token = crear_token_candidato(fila.propuesta.id, _candidato("magnet:?xt=otro"), SECRETO)
    r, reclamar, enviar = _descargar(fila, token)
    assert r.status_code == 200 and "caducado" in r.text
    reclamar.assert_not_called()
    enviar.assert_not_called()


def test_el_token_de_su_propia_propuesta_envia_lo_que_guarda_la_fila():
    fila = _fila("magnet:?xt=bueno")
    token = crear_token_candidato(fila.propuesta.id, fila.candidato, SECRETO)
    r, reclamar, enviar = _descargar(fila, token)
    assert r.status_code == 303 and "guardado=descargada" in r.headers["location"]
    reclamar.assert_awaited_once()
    enviado = enviar.await_args.args[0]
    assert enviado.download_url == "magnet:?xt=bueno"


def test_el_token_de_la_lista_se_liga_a_la_propuesta_no_al_numero():
    """La página genera el token con el id de la propuesta (si volviera a ser el del número,
    el de otra propuesta del mismo número valdría)."""
    fila = _fila()
    c = _cliente()
    try:
        with patch("zascarr.web.mejoras.listar_mejoras", AsyncMock(return_value=[fila])), \
             patch("zascarr.web.mejoras.get_settings",
                   return_value=SimpleNamespace(secret_key=SECRETO)):
            r = c.get("/ui/mejoras")
    finally:
        _cerrar()
    assert r.status_code == 200
    import re

    from zascarr.services.orchestrator import verificar_token_candidato
    token = re.search(r'name="token" value="([^"]+)"', r.text).group(1)
    assert verificar_token_candidato(token, fila.propuesta.id, SECRETO) is not None
    assert verificar_token_candidato(token, fila.issue.id, SECRETO) is None
