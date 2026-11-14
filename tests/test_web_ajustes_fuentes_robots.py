"""M-4 (#813): guardar Fuentes solo olvida el estado de robots de las fuentes que cambian."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.web.ajustes import _fuentes_de_robots_cambiadas

TODAS = ("fandom_dc", "fandom_marvel", "reading_orders", "continuity_guide",
         "comic_book_herald")


def _ajustes(**encendidas) -> SimpleNamespace:
    valores = {f"{fuente}_enabled": bool(encendidas.get(fuente, False)) for fuente in TODAS}
    return SimpleNamespace(**valores)


def _cliente():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def _preparar(monkeypatch, *, previas):
    guardar = AsyncMock()
    monkeypatch.setattr("zascarr.web.ajustes.RuntimeSettingsService",
                        lambda _db: SimpleNamespace(save=guardar))
    monkeypatch.setattr("zascarr.web.ajustes.get_settings",
                        lambda: _ajustes(**previas))
    olvidadas: list[str] = []
    monkeypatch.setattr("zascarr.utils.robots.olvidar_origenes_de_fuente",
                        lambda fuente: olvidadas.append(fuente) or ())
    return guardar, olvidadas


def _post(c, **flags):
    data = {f"{fuente}_enabled": "true" for fuente, valor in flags.items() if valor}
    return c.post("/ui/ajustes/guardar/fuentes", data=data)


def test_la_funcion_pura_detecta_solo_los_cambios():
    previas = {"fandom_dc": True, "fandom_marvel": False, "reading_orders": False}
    nuevas = {"fandom_dc": True, "fandom_marvel": True, "reading_orders": False}
    assert _fuentes_de_robots_cambiadas(previas, nuevas) == ("fandom_marvel",)


def test_cambiar_fandom_dc_olvida_solo_su_origen(monkeypatch):
    guardar, olvidadas = _preparar(monkeypatch, previas={"fandom_dc": False})
    c = _cliente()
    try:
        r = _post(c, fandom_dc=True)
    finally:
        _cerrar()
    assert r.status_code == 200
    guardar.assert_awaited_once()
    assert olvidadas == ["fandom_dc"]
    # La respuesta de guardado no expone secretos de otras tarjetas.
    assert "SECRETO" not in r.text and "password" not in r.text.lower()


def test_guardar_lo_mismo_no_olvida_nada(monkeypatch):
    guardar, olvidadas = _preparar(monkeypatch, previas={"fandom_dc": True})
    c = _cliente()
    try:
        r = _post(c, fandom_dc=True)
    finally:
        _cerrar()
    assert r.status_code == 200 and guardar.await_count == 1
    assert olvidadas == []


def test_apagar_una_fuente_olvida_solo_esa(monkeypatch):
    guardar, olvidadas = _preparar(monkeypatch, previas={
        "fandom_dc": True, "fandom_marvel": True, "reading_orders": True})
    c = _cliente()
    try:
        r = _post(c, fandom_dc=True, reading_orders=True)   # Marvel se apaga
    finally:
        _cerrar()
    assert r.status_code == 200
    assert olvidadas == ["fandom_marvel"]


def test_cambiar_varias_fuentes_olvida_cada_una(monkeypatch):
    guardar, olvidadas = _preparar(monkeypatch, previas={"fandom_dc": True,
                                                          "comic_book_herald": True})
    c = _cliente()
    try:
        r = _post(c, fandom_marvel=True, continuity_guide=True)  # DC y Herald se apagan
    finally:
        _cerrar()
    assert r.status_code == 200
    assert sorted(olvidadas) == ["comic_book_herald", "continuity_guide",
                                  "fandom_dc", "fandom_marvel"]


def test_si_el_guardado_falla_no_se_olvida(monkeypatch):
    guardar, olvidadas = _preparar(monkeypatch, previas={"fandom_dc": False})
    guardar.side_effect = RuntimeError("fallo de BD")
    c = _cliente()
    try:
        with pytest.raises(RuntimeError):
            _post(c, fandom_dc=True)
    finally:
        _cerrar()
    assert olvidadas == []
