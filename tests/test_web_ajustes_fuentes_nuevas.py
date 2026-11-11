"""Metron y Open Library en Ajustes: interruptores y token de Metron."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app


def _cliente():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_las_fuentes_nuevas_y_el_token_estan_en_ajustes(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes.get_settings", lambda: SimpleNamespace(
        comicvine_api_key="", comicvine_enabled=False, anilist_enabled=False,
        tebeosfera_enabled=False, gcd_enabled=False, metron_enabled=True,
        open_library_enabled=True, metron_token="tok", fuentes_heredadas=False,
        prowlarr_url="", prowlarr_api_key="", prowlarr_enabled=False,
        transmission_url="", transmission_username="", transmission_password="",
        transmission_enabled=False, amule_url="", amule_password="", amule_enabled=False,
        carpetas_compartidas=[], library_path="/lib", downloads_path="/dl",
        amule_incoming_dir="/in", auth_mode="none", auth_username="",
        auth_password_hash="", base_url="", webhook_enabled=False, webhook_type="generic",
        webhook_url="", webhook_token="", webhook_chat_id="", webhook_incluir_nombres=False,
        comicvine_rate_limit=1.0, anilist_rate_limit=1.5, tebeosfera_rate_limit=2.5,
        gcd_rate_limit=2.0, metron_rate_limit=3.0, open_library_rate_limit=1.0,
        forum_enabled=False, forum_ipb_url="", forum_ipb_api_key="", forum_username="",
        forum_password="", forum_rate_limit=6.0, forum_url=""))
    c = _cliente()
    try:
        r = c.get("/ui/ajustes")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'name="metron_enabled"' in r.text
    assert 'name="open_library_enabled"' in r.text
    assert 'name="metron_token"' in r.text and "Metron" in r.text


def test_guardar_fuentes_incluye_las_dos_nuevas(monkeypatch):
    guardar = AsyncMock()
    monkeypatch.setattr("zascarr.web.ajustes.RuntimeSettingsService",
                        lambda _db: SimpleNamespace(save=guardar))
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/guardar/fuentes", data={
            "metron_enabled": "true", "open_library_enabled": "true"})
    finally:
        _cerrar()
    assert r.status_code == 200
    valores = guardar.await_args.args[0]
    assert valores["metron_enabled"] is True and valores["open_library_enabled"] is True


def test_guardar_token_de_metron(monkeypatch):
    guardar = AsyncMock()
    monkeypatch.setattr("zascarr.web.ajustes.RuntimeSettingsService",
                        lambda _db: SimpleNamespace(save=guardar))
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/guardar/metron", data={"metron_token": "secreto"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert guardar.await_args.args[0] == {"metron_token": "secreto"}
