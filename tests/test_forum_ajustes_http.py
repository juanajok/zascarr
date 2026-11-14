"""SCR4 — tarjeta Foro en Ajustes y aviso HTTP sin TLS (AC-TLS-1…4)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.legal import current_legal_version


def _ajustes(**kw) -> SimpleNamespace:
    base = dict(
        comicvine_api_key="", comicvine_enabled=False, anilist_enabled=False,
        tebeosfera_enabled=False, gcd_enabled=False, metron_enabled=False,
        open_library_enabled=False, metron_token="", fuentes_heredadas=False,
        prowlarr_url="", prowlarr_api_key="", prowlarr_enabled=False,
        prowlarr_indexer_ids="", transmission_url="", transmission_username="",
        transmission_password="", transmission_enabled=False, amule_url="",
        amule_password="", amule_enabled=False, carpetas_compartidas=[],
        library_path="/lib", downloads_path="/dl", amule_incoming_dir="/in",
        auth_mode="none", auth_username="", auth_password_hash="", base_url="",
        webhook_enabled=False, webhook_type="generic", webhook_url="",
        webhook_token="", webhook_chat_id="", webhook_incluir_nombres=False,
        quality_profile="equilibrado", upgrade_scan_interval_minutes=360,
        upgrade_scan_batch=3, comicvine_rate_limit=1.0, anilist_rate_limit=1.5,
        tebeosfera_rate_limit=2.5, gcd_rate_limit=2.0, metron_rate_limit=3.0,
        open_library_rate_limit=1.0, forum_enabled=False, forum_username="",
        forum_password="", forum_rate_limit=2.0, forum_search_rate_limit=25.0,
        forum_url="", reading_orders_enabled=False, continuity_guide_enabled=False,
        fandom_dc_enabled=False, fandom_marvel_enabled=False,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _cliente():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_ac_tls_1_http_muestra_el_aviso_y_https_no(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes.get_settings", lambda: _ajustes(
        forum_url="http://foro.example/forum", forum_enabled=True))
    c = _cliente()
    try:
        r = c.get("/ui/ajustes")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "HTTP sin cifrar" in r.text and "no reutilices" in r.text.lower()
    assert 'name="forum_url"' in r.text and 'name="forum_password"' in r.text

    monkeypatch.setattr("zascarr.web.ajustes.get_settings", lambda: _ajustes(
        forum_url="https://foro.example/forum"))
    c = _cliente()
    try:
        r = c.get("/ui/ajustes")
    finally:
        _cerrar()
    assert "HTTP sin cifrar" not in r.text


def test_ac_tls_2_la_contrasena_configurada_no_llega_a_la_plantilla(monkeypatch):
    monkeypatch.setattr("zascarr.web.ajustes.get_settings", lambda: _ajustes(
        forum_url="http://foro.example/forum", forum_username="lector",
        forum_password="CLAVE_CANARIA", forum_enabled=True))
    c = _cliente()
    try:
        r = c.get("/ui/ajustes")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "CLAVE_CANARIA" not in r.text
    assert "member_id=" not in r.text and "pass_hash=" not in r.text
    assert "ya configurada — deja en blanco para no cambiarla" in r.text


def test_guardar_foro_con_contrasena_en_blanco_no_la_pisa(monkeypatch):
    guardar = AsyncMock()
    monkeypatch.setattr("zascarr.web.ajustes.RuntimeSettingsService",
                        lambda _db: SimpleNamespace(save=guardar))
    c = _cliente()
    try:
        r = c.post("/ui/ajustes/guardar/foro", data={
            "forum_url": "http://foro.example/forum/", "forum_username": " lector ",
            "forum_password": "", "forum_enabled": "true"})
    finally:
        _cerrar()
    assert r.status_code == 200
    valores = guardar.await_args.args[0]
    assert valores == {
        "forum_url": "http://foro.example/forum",
        "forum_username": "lector",
        "forum_password": "",              # el servicio ignora un secreto vacío
        "forum_enabled": True,
    }
    assert "CLAVE_CANARIA" not in r.text


def test_ac_tls_3_legal_advierte_del_http_sin_tls():
    from pathlib import Path

    legal = (Path(__file__).resolve().parents[1] / "src" / "zascarr" / "LEGAL.md")
    texto = legal.read_text(encoding="utf-8")
    assert "HTTP sin cifrar" in texto or "http://" in texto
    assert "sin protección" in texto or "no van protegidos" in texto
    assert "Aviso legal" in texto or "aviso legal" in texto
    # El hash que versiona la aceptación se recalcula solo (no hay constante a mano).
    assert len(current_legal_version()) == 16
