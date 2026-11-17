"""BL-OPS2 FR-40: una petición HTMX sin sesión no pinta /login dentro del fragmento."""
from __future__ import annotations

from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.main import app


def _con_password(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "auth_mode", "password")
    monkeypatch.setattr(s, "auth_password_hash", "pbkdf2_sha256$10000$00$" + "11" * 32)
    monkeypatch.setattr(s, "auth_session_version", 1)
    return s


def test_htmx_sin_sesion_recibe_hx_redirect_a_la_pagina_actual(monkeypatch):
    _con_password(monkeypatch)
    r = TestClient(app).get("/ui/copias/estado", headers={
        "HX-Request": "true", "HX-Current-URL": "/estado"})
    assert r.status_code == 200
    assert r.headers["hx-redirect"] == "/login?next=%2Festado"
    assert r.content == b""


def test_htmx_con_url_hostil_usa_la_raiz(monkeypatch):
    _con_password(monkeypatch)
    for actual in ("//evil.example/x", "https://evil.example/x", "javascript:x", ""):
        r = TestClient(app).get("/ui/copias/estado", headers={
            "HX-Request": "true", "HX-Current-URL": actual})
        assert r.headers["hx-redirect"] == "/login?next=%2F"


def test_no_htmx_sigue_siendo_303(monkeypatch):
    _con_password(monkeypatch)
    r = TestClient(app).get("/ui/copias/estado", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login?next=")
