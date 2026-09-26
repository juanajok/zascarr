"""
tests/test_web_auth.py

Suite de /login y /logout (A6): contrato HTTP del formulario, nunca la
lógica de credenciales_validas() en sí (ya cubierta en test_auth.py).
AuthMiddleware (global) queda en "none" en estos tests salvo que se
monkeypatchee — no hace falta cookie ni Basic Auth para llegar a /login,
que está exento (services/auth.py).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.main import app
from zascarr.services.auth import COOKIE_NAME, hash_password


@pytest.fixture
def restaurar_settings():
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    originales = {campo: getattr(s, campo) for campo in _ALL_FIELDS}
    yield
    for campo, valor in originales.items():
        setattr(s, campo, valor)


class TestLoginForm:

    def test_auth_mode_none_redirige_sin_pedir_nada(self, restaurar_settings):
        get_settings().auth_mode = "none"
        client = TestClient(app, follow_redirects=False)
        r = client.get("/login")
        assert r.status_code in (302, 303, 307)

    def test_modo_password_muestra_solo_contrasena(self, restaurar_settings):
        get_settings().auth_mode = "password"
        client = TestClient(app)
        r = client.get("/login")
        assert r.status_code == 200
        assert 'name="password"' in r.text
        assert 'name="username"' not in r.text

    def test_modo_user_password_pide_tambien_usuario(self, restaurar_settings):
        get_settings().auth_mode = "user_password"
        client = TestClient(app)
        r = client.get("/login")
        assert r.status_code == 200
        assert 'name="username"' in r.text

    def test_next_externo_no_se_refleja_tal_cual(self, restaurar_settings):
        """Open redirect: un `next` que no sea una ruta relativa de este
        sitio se descarta, nunca se usa tal cual en el formulario."""
        get_settings().auth_mode = "password"
        client = TestClient(app)
        r = client.get("/login", params={"next": "https://sitio-falso.example/robar"})
        assert "sitio-falso.example" not in r.text


class TestLoginSubmit:

    def test_credenciales_correctas_ponen_cookie_y_redirigen(self, restaurar_settings):
        get_settings().auth_mode = "password"
        get_settings().auth_password_hash = hash_password("secreta123")
        get_settings().secret_key = "clave-de-prueba"
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={"password": "secreta123", "next": "/ui/"})

        assert r.status_code == 303
        assert r.headers["location"] == "/ui/"
        assert COOKIE_NAME in r.cookies

    def test_credenciales_incorrectas_no_ponen_cookie(self, restaurar_settings):
        get_settings().auth_mode = "password"
        get_settings().auth_password_hash = hash_password("secreta123")
        get_settings().secret_key = "clave-de-prueba"
        client = TestClient(app)

        r = client.post("/login", data={"password": "mala", "next": "/ui/"})

        assert r.status_code == 401
        assert "incorrectos" in r.text.lower()
        assert COOKIE_NAME not in r.cookies

    def test_next_externo_en_el_submit_tampoco_redirige_fuera(self, restaurar_settings):
        get_settings().auth_mode = "password"
        get_settings().auth_password_hash = hash_password("secreta123")
        get_settings().secret_key = "clave-de-prueba"
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={
            "password": "secreta123", "next": "https://sitio-falso.example/robar",
        })

        assert r.status_code == 303
        assert r.headers["location"] == "/"


class TestLogout:

    def test_borra_la_cookie_y_redirige_a_login(self, restaurar_settings):
        client = TestClient(app, follow_redirects=False)
        r = client.post("/logout")
        assert r.status_code == 303
        assert r.headers["location"] == "/login"
        assert client.cookies.get(COOKIE_NAME) is None
