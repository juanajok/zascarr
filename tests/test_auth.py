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

    @pytest.mark.asyncio
    async def test_verifica_la_contrasena_correcta(self):
        stored = hash_password("correcta123")
        assert await verify_password("correcta123", stored) is True

    @pytest.mark.asyncio
    async def test_rechaza_la_contrasena_incorrecta(self):
        stored = hash_password("correcta123")
        assert await verify_password("otra-cosa", stored) is False

    def test_dos_hashes_de_la_misma_contrasena_son_distintos(self):
        """Sal aleatoria por hash — nunca el mismo valor almacenado dos
        veces para la misma contraseña (evita comparar hashes por igualdad
        directa y filtrar quién tiene la misma contraseña que otro)."""
        assert hash_password("igual") != hash_password("igual")

    @pytest.mark.asyncio
    async def test_stored_vacio_o_malformado_nunca_revienta(self):
        assert await verify_password("x", "") is False
        assert await verify_password("x", "no-tiene-el-formato-esperado") is False
        assert await verify_password("x", "otro_algo$1$aa$bb") is False

    @pytest.mark.asyncio
    async def test_pbkdf2_corre_fuera_del_bucle_de_eventos(self, monkeypatch):
        """Caso 6 de la ficha de seguridad: el PBKDF2 no corre en el hilo del
        bucle de eventos (la Pi no puede congelarse con cada Basic)."""
        import hashlib
        import threading

        stored = hash_password("secreta")   # real, en el hilo principal (no se registra)
        hilos: list = []
        real = hashlib.pbkdf2_hmac

        def espia(*args, **kwargs):
            hilos.append(threading.current_thread())
            return real(*args, **kwargs)

        monkeypatch.setattr("zascarr.services.auth.hashlib.pbkdf2_hmac", espia)

        assert await verify_password("secreta", stored) is True

        assert hilos, "el PBKDF2 debería haberse ejecutado"
        assert all(h is not threading.main_thread() for h in hilos)
        # El nombre del hilo prueba que se usó el ejecutor PROPIO, no el
        # `to_thread` por defecto (que correría en el ejecutor general).
        assert all(h.name.startswith("pbkdf2") for h in hilos)


class TestCredencialesValidas:

    @pytest.mark.asyncio
    async def test_modo_none_nunca_valida_nada(self):
        settings = get_settings().model_copy(update={"auth_mode": "none"})
        assert await credenciales_validas("", "", settings) is False
        assert await credenciales_validas("admin", "loquesea", settings) is False

    @pytest.mark.asyncio
    async def test_modo_password_ignora_el_usuario(self):
        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("secreta"),
        })
        assert await credenciales_validas("cualquiera", "secreta", settings) is True
        assert await credenciales_validas("", "secreta", settings) is True
        assert await credenciales_validas("cualquiera", "mala", settings) is False

    @pytest.mark.asyncio
    async def test_modo_user_password_exige_ambos(self):
        settings = get_settings().model_copy(update={
            "auth_mode": "user_password", "auth_username": "juanjo",
            "auth_password_hash": hash_password("secreta"),
        })
        assert await credenciales_validas("juanjo", "secreta", settings) is True
        assert await credenciales_validas("otro", "secreta", settings) is False
        assert await credenciales_validas("juanjo", "mala", settings) is False

    @pytest.mark.asyncio
    async def test_nombre_de_usuario_no_ascii_no_revienta(self):
        """Regresión: `hmac.compare_digest` con `str` no-ASCII lanzaba
        `TypeError` y un nombre con tilde/ñ daba 500."""
        settings = get_settings().model_copy(update={
            "auth_mode": "user_password", "auth_username": "juánjo",
            "auth_password_hash": hash_password("secreta"),
        })
        assert await credenciales_validas("juánjo", "secreta", settings) is True
        assert await credenciales_validas("juánjo", "mala", settings) is False

    @pytest.mark.asyncio
    async def test_sin_hash_configurado_nunca_valida(self):
        """No debe poder 'colarse' con una contraseña vacía solo porque
        auth_password_hash también está vacío."""
        settings = get_settings().model_copy(update={"auth_mode": "password", "auth_password_hash": ""})
        assert await credenciales_validas("", "", settings) is False

    @pytest.mark.asyncio
    async def test_verify_password_se_llama_siempre_sin_hash_configurado(self, monkeypatch):
        """Hallazgo de revisión (timing side-channel): con un `and`
        normal, auth_password_hash vacío cortaba ANTES de llamar a
        verify_password() (PBKDF2) — una respuesta instantánea delataba
        "este modo no tiene contraseña puesta" sin falta ver el resultado.
        Ahora debe llamarse siempre, contra un hash de relleno si hace
        falta, para que el coste sea el mismo se acierte o no."""
        llamadas: list = []
        real = verify_password

        async def espia(password, stored):
            llamadas.append(True)
            return await real(password, stored)

        monkeypatch.setattr("zascarr.services.auth.verify_password", espia)
        settings = get_settings().model_copy(update={"auth_mode": "password", "auth_password_hash": ""})

        assert await credenciales_validas("", "cualquiera", settings) is False
        assert len(llamadas) == 1

    @pytest.mark.asyncio
    async def test_verify_password_se_llama_siempre_con_usuario_incorrecto(self, monkeypatch):
        """Mismo hallazgo, en user_password: un usuario que no coincide
        no debe evitar el coste de PBKDF2 — si no, medir el tiempo de
        respuesta permitiría averiguar qué nombres de usuario existen."""
        llamadas: list = []
        real = verify_password

        async def espia(password, stored):
            llamadas.append(True)
            return await real(password, stored)

        monkeypatch.setattr("zascarr.services.auth.verify_password", espia)
        settings = get_settings().model_copy(update={
            "auth_mode": "user_password", "auth_username": "juanjo",
            "auth_password_hash": hash_password("secreta"),
        })

        assert await credenciales_validas("no-es-juanjo", "secreta", settings) is False
        assert len(llamadas) == 1


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
        from zascarr.services.auth import sign_token
        token_viejo = sign_token(vieja, "mi-secreto")
        assert sesion_valida(token_viejo, "mi-secreto") is False


def _app_de_prueba() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AuthMiddleware)

    @app.get("/ui/algo")
    def _algo():
        return {"ok": True}

    @app.post("/ui/algo")
    def _algo_post():
        return {"ok": True}

    @app.get("/api/algo")
    def _api_algo():
        return {"ok": True}

    @app.post("/api/algo")
    def _api_algo_post():
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

    def test_next_con_ampersand_se_codifica(self, monkeypatch):
        """Caso 3 de la ficha de seguridad: un `&` en la query original no se
        trunca al redirigir a /login (antes se parseaba como parámetro aparte)."""
        from urllib.parse import parse_qs, urlsplit

        settings = get_settings().model_copy(update={
            "auth_mode": "password", "auth_password_hash": hash_password("x"), "secret_key": "s",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba(), follow_redirects=False)

        r = client.get("/ui/algo?q=a&b=2")

        assert r.status_code == 303
        params = parse_qs(urlsplit(r.headers["location"]).query)
        assert params["next"] == ["/ui/algo?q=a&b=2"]


@pytest.mark.sin_origen
class TestOrigenHost:
    """CSRF / Origen / Host (ficha de seguridad). Marcado `sin_origen` para
    controlar Host/Origin a mano en vez de heredar el localhost del conftest."""

    @staticmethod
    def _cliente(monkeypatch, *, base_url="http://127.0.0.1:8000", settings_base_url=""):
        settings = get_settings().model_copy(update={
            "auth_mode": "none", "secret_key": "s", "base_url": settings_base_url,
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        return TestClient(_app_de_prueba(), base_url=base_url)

    def test_get_no_se_comprueba(self, monkeypatch):
        r = self._cliente(monkeypatch).get("/ui/algo")
        assert r.status_code == 200

    def test_post_ui_sin_origin_se_bloquea(self, monkeypatch):
        r = self._cliente(monkeypatch).post("/ui/algo")
        assert r.status_code == 403

    def test_post_api_sin_origin_se_permite(self, monkeypatch):
        r = self._cliente(monkeypatch).post("/api/algo")
        assert r.status_code == 200

    def test_origin_del_mismo_host_se_acepta(self, monkeypatch):
        r = self._cliente(monkeypatch).post(
            "/ui/algo", headers={"Origin": "http://127.0.0.1:8000"})
        assert r.status_code == 200

    def test_origin_ajeno_se_rechaza(self, monkeypatch):
        r = self._cliente(monkeypatch).post(
            "/ui/algo", headers={"Origin": "https://mal.example"})
        assert r.status_code == 403

    def test_origin_null_se_rechaza(self, monkeypatch):
        r = self._cliente(monkeypatch).post("/ui/algo", headers={"Origin": "null"})
        assert r.status_code == 403

    def test_sec_fetch_site_cross_site_se_rechaza(self, monkeypatch):
        r = self._cliente(monkeypatch).post(
            "/ui/algo",
            headers={"Origin": "http://127.0.0.1:8000", "Sec-Fetch-Site": "cross-site"})
        assert r.status_code == 403

    def test_origin_igual_a_base_url_con_host_distinto_se_acepta(self, monkeypatch):
        """Proxy inverso: nginx cambia Host, Origin es el dominio público."""
        r = self._cliente(
            monkeypatch,
            base_url="http://127.0.0.1:8000",
            settings_base_url="https://comics.example").post(
            "/ui/algo", headers={"Origin": "https://comics.example"})
        assert r.status_code == 200

    def test_host_con_ip_literal_se_permite(self, monkeypatch):
        r = self._cliente(monkeypatch, base_url="http://192.168.1.50:8000").post(
            "/ui/algo", headers={"Origin": "http://192.168.1.50:8000"})
        assert r.status_code == 200

    def test_host_con_nombre_ajeno_se_rechaza(self, monkeypatch):
        """DNS rebinding: un nombre de dominio que resuelve a la IP local."""
        r = self._cliente(monkeypatch, base_url="http://atacante.example").post(
            "/ui/algo", headers={"Origin": "http://atacante.example"})
        assert r.status_code == 403

    def test_referer_con_sufijo_enganoso_no_pasa(self, monkeypatch):
        r = self._cliente(monkeypatch).post(
            "/ui/algo", headers={"Referer": "https://example.org.attacker.com/x"})
        assert r.status_code == 403

    def test_el_403_dice_la_salida_en_espanol(self, monkeypatch):
        r = self._cliente(monkeypatch).post(
            "/ui/algo", headers={"Origin": "https://mal.example"})
        assert r.status_code == 403
        assert "BASE_URL" in r.text and "proxy" in r.text

    def test_host_ipv6_loopback_se_permite(self, monkeypatch):
        """`[::1]:8000` no se puede parsear con split(':')."""
        r = self._cliente(monkeypatch, base_url="http://[::1]:8000").post(
            "/ui/algo", headers={"Origin": "http://[::1]:8000"})
        assert r.status_code == 200

    def test_host_ipv6_link_local_se_permite(self, monkeypatch):
        r = self._cliente(monkeypatch, base_url="http://[fe80::1]:8000").post(
            "/ui/algo", headers={"Origin": "http://[fe80::1]:8000"})
        assert r.status_code == 200

    def test_origin_con_puerto_invalido_da_403_no_500(self, monkeypatch):
        r = self._cliente(monkeypatch).post(
            "/ui/algo", headers={"Origin": "http://x:99999"})
        assert r.status_code == 403

    def test_host_en_allowed_hosts_se_permite(self, monkeypatch):
        """Quien entra por el nombre de su equipo no debe recibir 403."""
        settings = get_settings().model_copy(update={
            "auth_mode": "none", "secret_key": "s",
            "allowed_hosts": "raspberrypi.local,pi",
        })
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba(), base_url="http://raspberrypi.local:8000")

        r = client.post("/ui/algo", headers={"Origin": "http://raspberrypi.local:8000"})

        assert r.status_code == 200

    def test_get_con_host_ajeno_se_rechaza(self, monkeypatch):
        """Rebinding de LECTURA: un GET con Host ajeno también se rechaza (si no,
        un atacante podría leer biblioteca/wishlist/ajustes)."""
        r = self._cliente(monkeypatch, base_url="http://atacante.example").get("/ui/algo")
        assert r.status_code == 403

    def test_el_403_de_host_dice_allowed_hosts(self, monkeypatch):
        r = self._cliente(monkeypatch, base_url="http://atacante.example").get("/ui/algo")
        assert r.status_code == 403
        assert "ALLOWED_HOSTS" in r.text

    def test_same_origin_cubre_el_proxy_con_tls(self, monkeypatch):
        """Caddy conserva Host pero la app ve http; el navegador manda
        `Sec-Fetch-Site: same-origin` (que no puede falsificar una página) y eso
        evita el 403 con `auth_mode=password` (sin comprobación de Host)."""
        settings = get_settings().model_copy(update={"auth_mode": "password", "secret_key": "s"})
        monkeypatch.setattr("zascarr.services.auth.get_settings", lambda: settings)
        client = TestClient(_app_de_prueba(), base_url="http://zascarr.example",
                            follow_redirects=False)
        r = client.post(
            "/ui/algo",
            headers={"Origin": "https://zascarr.example", "Sec-Fetch-Site": "same-origin"})
        # Pasa el middleware (no 403); el 303 es el redirect de auth, no el CSRF.
        assert r.status_code == 303


class TestAppRealConHtmx:
    """La UI real (zascarr.main.app) con las cabeceras de HTMX no debe caer en el
    403 del middleware. No marcado `sin_origen`: usa el localhost del conftest."""

    def _cliente(self):
        from zascarr.main import app as app_real
        return TestClient(app_real, follow_redirects=False)

    def test_post_htmx_con_origen_del_mismo_host_no_es_403(self):
        # /login es un POST de estado y no toca la BD con auth_mode=none.
        r = self._cliente().post(
            "/login", data={"next": "/", "username": "", "password": ""},
            headers={"HX-Request": "true", "Origin": "http://localhost"})
        assert r.status_code != 403

    def test_post_desde_ip_de_la_lan_no_es_403(self):
        r = self._cliente().post(
            "/login", data={"next": "/", "username": "", "password": ""},
            headers={"Host": "192.168.1.50:8000", "Origin": "http://192.168.1.50:8000"})
        assert r.status_code != 403
