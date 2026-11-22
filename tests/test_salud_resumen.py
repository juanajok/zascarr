"""UXA-08d (#1219): el punto de aviso del menú refleja la última comprobación de salud.

El menú nunca sondea: lee el veredicto que `GET /api/health` dejó en `services/salud_resumen.py`.
"""
from __future__ import annotations

import re
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import salud_resumen
from zascarr.services.salud_resumen import EDAD_MAXIMA_S, registrar, requiere_atencion
from zascarr.web import navegacion

# ── el resumen ────────────────────────────────────────────────────────────────────────────


def test_sin_resumen_no_se_enciende_nada():
    assert requiere_atencion() is False


@pytest.mark.parametrize("estado, enciende", [
    ("healthy", False), ("degraded", True), ("unhealthy", True), ("unreachable", False)])
def test_solo_atencion_y_error_encienden_el_punto(estado, enciende):
    registrar(estado, ahora=1000.0)
    assert requiere_atencion(ahora=1001.0) is enciende


def test_un_resumen_viejo_no_se_cree():
    registrar("degraded", ahora=1000.0)
    assert requiere_atencion(ahora=1000.0 + EDAD_MAXIMA_S) is True
    assert requiere_atencion(ahora=1000.0 + EDAD_MAXIMA_S + 0.1) is False


def test_un_reloj_que_va_hacia_atras_no_enciende():
    registrar("degraded", ahora=1000.0)
    assert requiere_atencion(ahora=900.0) is False


def test_la_ultima_comprobacion_manda():
    registrar("degraded", ahora=1000.0)
    registrar("healthy", ahora=1010.0)
    assert requiere_atencion(ahora=1011.0) is False


def test_solo_se_guarda_el_veredicto_no_detalles():
    registrar("degraded", ahora=1.0)
    assert set(vars(salud_resumen._ultimo)) == {"estado", "momento"}


# ── /api/health lo registra ───────────────────────────────────────────────────────────────


class _Sesion:
    async def execute(self, _statement):
        return None


def _health(monkeypatch, *, amule_ok: bool, amule_on: bool = True):
    monkeypatch.setattr(get_settings(), "transmission_enabled", False)
    monkeypatch.setattr(get_settings(), "amule_enabled", amule_on)

    async def _get_db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _get_db
    try:
        with (
            patch("zascarr.api.health._check_amule", AsyncMock(return_value=amule_ok)),
            patch("zascarr.api.health._database_status",
                  AsyncMock(return_value=("ok", "Conectada y migrada."))),
        ):
            return TestClient(app).get("/api/health").json()
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_health_registra_degraded_y_el_menu_lo_ve(monkeypatch):
    assert _health(monkeypatch, amule_ok=False)["status"] == "degraded"
    assert requiere_atencion() is True


def test_un_servicio_apagado_en_ajustes_no_enciende_el_punto(monkeypatch):
    cuerpo = _health(monkeypatch, amule_ok=False, amule_on=False)
    assert cuerpo["checks"]["amule"] == "disabled"
    assert cuerpo["status"] == "healthy"
    assert requiere_atencion() is False


def test_health_que_vuelve_a_healthy_apaga_el_punto(monkeypatch):
    _health(monkeypatch, amule_ok=False)
    assert requiere_atencion() is True
    assert _health(monkeypatch, amule_ok=True)["status"] == "healthy"
    assert requiere_atencion() is False


# ── el fragmento del menú ─────────────────────────────────────────────────────────────────


class _FabricaDeSesiones:
    def __call__(self):
        return self

    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc):
        return False


def _fragmento(monkeypatch, variante="a"):
    monkeypatch.setattr(navegacion, "async_session_factory", _FabricaDeSesiones())
    monkeypatch.setattr(navegacion, "contadores",
                        AsyncMock(return_value=SimpleNamespace(pendientes=0, deseados=0)))
    monkeypatch.setattr(get_settings(), "nav_movil_variante", variante)
    navegacion._calculo_en_curso = None
    try:
        return TestClient(app).get("/ui/_nav/estado").text
    finally:
        navegacion._calculo_en_curso = None


def _visible(html, ident):
    etiqueta = re.search(rf'<span id="{ident}"[^>]*>', html)
    assert etiqueta, f"falta {ident}"
    return " hidden" not in etiqueta.group(0)


def test_sin_resumen_el_punto_de_estado_esta_oculto(monkeypatch):
    assert _visible(_fragmento(monkeypatch), "cnt-estado") is False


def test_con_resumen_degraded_el_punto_de_estado_se_enciende_con_texto_accesible(monkeypatch):
    registrar("degraded")
    html = _fragmento(monkeypatch)
    assert _visible(html, "cnt-estado") is True
    assert "necesita atención" in html


def test_variante_b_enciende_tambien_el_punto_de_mas(monkeypatch):
    registrar("unhealthy")
    html = _fragmento(monkeypatch, "b")
    assert _visible(html, "cnt-mas") is True and _visible(html, "cnt-estado") is True
    assert "Más: necesita atención" in html


def test_variante_a_no_toca_mas(monkeypatch):
    registrar("degraded")
    assert 'id="cnt-mas"' not in _fragmento(monkeypatch, "a")


def test_resumen_viejo_en_el_fragmento_no_enciende(monkeypatch):
    registrar("degraded", ahora=0.0)  # el reloj monotónico real está muy por delante
    assert _visible(_fragmento(monkeypatch), "cnt-estado") is False


def test_la_seguridad_sigue_encendiendo_el_punto_sin_resumen(monkeypatch):
    monkeypatch.setattr(navegacion, "estado_de_seguridad", lambda: {"atencion": True})
    assert _visible(_fragmento(monkeypatch), "cnt-estado") is True


def test_el_menu_no_sondea_servicios(monkeypatch):
    """El fragmento solo lee el resumen: no llama a ninguna comprobación de salud."""
    sonda = AsyncMock()
    monkeypatch.setattr("zascarr.api.health._check_transmission", sonda)
    monkeypatch.setattr("zascarr.api.health._check_amule", sonda)
    monkeypatch.setattr("zascarr.api.health._database_status", sonda)
    registrar("degraded")
    _fragmento(monkeypatch)
    sonda.assert_not_called()
