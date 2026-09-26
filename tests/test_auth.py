"""
tests/test_auth.py

Suite de autenticación (A6): hash/verificación de contraseña (PBKDF2,
stdlib), firma/verificación de la cookie de sesión (HMAC, stdlib),
credenciales_validas() para los tres modos, y el propio AuthMiddleware
— probado contra una app FastAPI mínima y aislada (no zascarr.main.app,
para no arriesgar fugas sobre el Settings real compartido entre tests,
ver nota de aislamiento en runtime_settings D11) con get_settings()
monkeypatcheado, mismo patrón que ya usa test_orchestrator.py.
"""
from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.services.auth import (
    COOKIE_NAME,
    AuthMiddleware,
    credenciales_validas,
    crear_cookie_sesion,
    hash_password,
    sesion_valida,
    verify_password,
)


class TestHashPassword:

    def test_verifica_la_contrasena_correcta(self):
        stored = hash_password("correcta123")
        assert verify_password("correcta123", stored) is True

    def test_rechaza_la_contrasena_incorrecta(self):
        stored = hash_password("correcta123")
        assert verify_password("otra-cosa", stored) is False

    def test_dos_hashes_de_la_misma_contrasena_son_distintos(self):
        """Sal aleatoria por hash — nunca el mismo valor almacenado dos
        veces para la misma contraseña (evita comparar hashes por igualdad
        directa y filtrar quién tiene la misma contraseña que otro)."""
        assert hash_password("igual") != hash_password("igual")

    def test_stored_vacio_o_malformado_nunca_revienta(self):
        assert verify_password("x", "") is False
        assert verify_password("x", "no-tiene-el-formato-esperado") is False
        assert verify_password("x", "otro_algo$1$aa$bb") is False


class TestCredencialesValidas:

    def test_modo_none_nunca_valida_nada(self):
        settings = get_settings().model_copy(update={"auth_mode": "none"})
        assert credenciales_validas("", "", settings) is False
        assert credenciales_validas("admin", "loquesea", settings) is False

    def test_modo_password_ignora_el_usuario(self):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"),
        })
        assert credenciales_validas("cualquiera", "secreta", settings) is True
        assert credenciales_validas("", "secreta", settings) is True
        assert credenciales_validas("cualquiera", "mala", settings) is False

    def test_modo_user_password_exige_ambos(self):
        settings = get_settings().model_copy(update={
            "auth_mode": "user_password", "auth_username": "juanjo",
            "auth_password_hash": hash_password("secreta"),
        })
        assert credenciales_validas("juanjo", "secreta", settings) is True
        assert credenciales_validas("otro", "secreta", settings) is False
        assert credenciales_validas("juanjo", "mala", settings) is False

    def test_sin_hash_configurado_nunca_valida(self):
        """No debe poder 'colarse' con una contraseña vacía solo porque
        auth_password_hash también está vacío."""
        settings = get_settings().model_copy(update={"auth_mode": "password", "auth_password_hash": ""})
        assert credenciales_validas("", "", settings) is False


class TestCookieSesion:

    def test_cookie_recien_creada_es_valida(self):
        token = crear_cookie_sesion("mi-secreto")
        assert sesion_valida(token, "mi-secreto") is True

    def test_cookie_firmada_con_otro_secreto_no_vale(self):
        token = crear_cookie_sesion("mi-secreto")
        assert sesion_valida(token, "otro-secreto-distinto") is False

    def test_cookie_manipulada_no_vale(self):
        token = crear_cookie_sesion("mi-secreto")
        payload, _, mac = token.rpartition(".")
        manipulada = f"{int(payload) + 999999}.{mac}"
        assert sesion_valida(manipulada, "mi-secreto") is False

    def test_cookie_ausente_o_vacia_no_vale(self):
        assert sesion_valida(None, "mi-secreto") is False
        assert sesion_valida("", "mi-secreto") is False

    def test_cookie_expirada_no_vale(self, monkeypatch):
        token = crear_cookie_sesion("mi-secreto")
        monkeypatch.setattr("zascarr.services.auth.SESSION_MAX_AGE", 1)
        # Reconstruye el mismo payload pero con una emisión ya vieja.
        vieja = f"{int(time.time()) - 100}"
        from zascarr.services.auth import _sign
        token_viejo = _sign(vieja, "mi-secreto")
        assert sesion_valida(token_viejo, "mi-secreto") is False


def _app_de_prueba() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/ui/algo")
    def _algo():
        return {"ok": True}

    @app.get("/api/algo")
    def _api_algo():
        return {"ok": True}

    @app.get("/api/health")
    def _health():
        return {"status": "ok"}

    @app.get("/legal")
    def _legal():
        return "aviso legal"

    @app.get("/login")
    def _login():
        return "formulario de login"

    return app


class TestAuthMiddleware:

    def test_auth_mode_none_no_toca_nada(self, monkeypatch):
        settings = get_settings().model_copy(update={"auth_mode": "none"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba())

        r = client.get("/ui/algo")

        assert r.status_code == 200

    def test_ruta_ui_sin_sesion_redirige_a_login(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("x"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba(), follow_redirects=False)

        r = client.get("/ui/algo")

        assert r.status_code == 303
        assert r.headers["location"].startswith("/login?next=")

    def test_ruta_api_sin_sesion_da_401_con_www_authenticate(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("x"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba())

        r = client.get("/api/algo")

        assert r.status_code == 401
        assert "Basic" in r.headers["www-authenticate"]

    def test_rutas_exentas_no_piden_nada(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("x"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba())

        assert client.get("/api/health").status_code == 200
        assert client.get("/legal").status_code == 200
        assert client.get("/login").status_code == 200

    def test_cookie_de_sesion_valida_deja_pasar(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("x"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba())
        client.cookies.set(COOKIE_NAME, crear_cookie_sesion("s"))

        r = client.get("/ui/algo")

        assert r.status_code == 200

    def test_basic_auth_valido_deja_pasar_una_api(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba())

        r = client.get("/api/algo", auth=("cualquiera", "secreta"))

        assert r.status_code == 200

    def test_basic_auth_invalido_no_deja_pasar(self, monkeypatch):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba())

        r = client.get("/api/algo", auth=("cualquiera", "mala"))

        assert r.status_code == 401
