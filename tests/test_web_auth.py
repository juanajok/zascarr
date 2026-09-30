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
from zascarr.web.auth import _next_seguro


@pytest.fixture
def restaurar_settings():
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    originales = {campo: getattr(s, campo) for campo in _ALL_FIELDS}
    yield
    for campo, valor in originales.items():
        setattr(s, campo, valor)


class _FakeSession:
    """Sesión mínima: /login ahora depende de get_db por el rehasheo. La fila es
    real (`RuntimeSetting`) para poder inspeccionar lo guardado."""

    def __init__(self):
        from zascarr.models import RuntimeSetting
        self.fila = RuntimeSetting(id=1, values={})

    async def execute(self, _statement):
        from unittest.mock import MagicMock
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self.fila)
        return result

    def add(self, obj):
        self.fila = obj

    async def flush(self):
        return None


@pytest.fixture
def db_fake():
    return _FakeSession()


@pytest.fixture(autouse=True)
def _db_falsa(db_fake):
    from zascarr.database import get_db

    async def _get_db():
        yield db_fake

    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


def _hash_con_iteraciones(password: str, iterations: int) -> str:
    """Hash PBKDF2 con un número de iteraciones concreto — simula uno guardado
    antes de subir el contador (el que dispara el rehasheo al iniciar sesión)."""
    import hashlib
    import secrets
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


class TestNextSeguro:
    """A6 (revisión 2026-09-26): `next` solo acepta rutas relativas de este
    sitio. El caso de la barra invertida ('/\\host') se normaliza a '//host'
    en un navegador (WHATWG URL) y debe descartarse igual que un dominio
    absoluto — la versión anterior lo dejaba pasar."""

    def test_ruta_relativa_se_mantiene(self):
        assert _next_seguro("/ui/") == "/ui/"

    def test_doble_barra_se_descarta(self):
        assert _next_seguro("//host.invalid") == "/"

    def test_barra_invertida_se_descarta(self):
        assert _next_seguro(r"/\host.invalid") == "/"

    def test_backslash_inicial_se_descarta(self):
        assert _next_seguro(r"\host.invalid") == "/"

    def test_url_absoluta_se_descarta(self):
        assert _next_seguro("https://host.invalid/x") == "/"


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

    def test_next_barra_invertida_no_se_refleja_tal_cual(self, restaurar_settings):
        """A6: '/\\host' se normaliza a '//host' en el navegador — también
        debe descartarse, no reflejarse en el formulario."""
        get_settings().auth_mode = "password"
        client = TestClient(app)
        r = client.get("/login", params={"next": r"/\sitio-falso.example"})
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

    def test_next_barra_invertida_en_submit_redirige_a_raiz(self, restaurar_settings):
        """A6: el '/\\host' en el POST tampoco puede colar un destino externo."""
        get_settings().auth_mode = "password"
        get_settings().auth_password_hash = hash_password("secreta123")
        get_settings().secret_key = "clave-de-prueba"
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={
            "password": "secreta123", "next": r"/\sitio-falso.example",
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


class TestRehasheoYSesion:
    """`auth_session_version` (ficha de seguridad): la cookie lleva la versión
    firmada; el rehasheo por iteraciones NO la toca, cambiar la contraseña sí."""

    @pytest.fixture
    def _settings_password(self, restaurar_settings):
        get_settings().auth_mode = "password"
        get_settings().secret_key = "clave-de-prueba"
        get_settings().auth_session_version = 0
        yield

    @pytest.mark.asyncio
    async def test_el_rehasheo_no_invalida_la_sesion(self, _settings_password, db_fake):
        from zascarr.services.auth import necesita_rehash, sesion_valida, verify_password

        viejo = _hash_con_iteraciones("secreta123", 1000)
        get_settings().auth_password_hash = viejo
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={"password": "secreta123", "next": "/ui/"})

        assert r.status_code == 303
        # El hash se rehizo con las iteraciones actuales...
        nuevo = db_fake.fila.values["auth_password_hash"]
        assert nuevo != viejo
        assert necesita_rehash(nuevo) is False
        assert await verify_password("secreta123", nuevo) is True
        # ...y la versión NO cambia: la cookie emitida sigue siendo válida.
        assert get_settings().auth_session_version == 0
        assert sesion_valida(r.cookies[COOKIE_NAME], "clave-de-prueba", 0) is True

    def test_hash_ya_al_dia_no_se_toca(self, _settings_password, db_fake):
        get_settings().auth_password_hash = hash_password("secreta123")
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={"password": "secreta123", "next": "/ui/"})

        assert r.status_code == 303
        assert "auth_password_hash" not in db_fake.fila.values

    @pytest.mark.asyncio
    async def test_dos_logins_simultaneos_que_rehashean_no_se_pisan(self, _settings_password):
        """Si el rehasheo subiera la versión, dos logins a la vez se invalidarían
        el uno al otro. Ahora ambos escriben un hash válido de la MISMA
        contraseña y la versión se queda igual."""
        import threading
        from concurrent.futures import ThreadPoolExecutor

        from zascarr.database import get_db
        from zascarr.services.auth import necesita_rehash, sesion_valida, verify_password

        viejo = _hash_con_iteraciones("secreta123", 1000)
        get_settings().auth_password_hash = viejo

        sesion = _FakeSession()

        async def _get_db():
            yield sesion

        app.dependency_overrides[get_db] = _get_db
        barrera = threading.Barrier(2)

        def _login():
            client = TestClient(app, follow_redirects=False)
            barrera.wait(timeout=5)
            return client.post("/login", data={"password": "secreta123", "next": "/ui/"})

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                resultados = list(pool.map(lambda _: _login(), range(2)))
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert all(r.status_code == 303 for r in resultados)
        assert get_settings().auth_session_version == 0
        nuevo = sesion.fila.values["auth_password_hash"]
        assert necesita_rehash(nuevo) is False
        assert await verify_password("secreta123", nuevo) is True
        for r in resultados:
            assert sesion_valida(r.cookies[COOKIE_NAME], "clave-de-prueba", 0) is True

    @pytest.mark.asyncio
    async def test_cambio_de_contrasena_durante_el_rehasheo_no_resucita_la_sesion(
            self, _settings_password, db_fake, monkeypatch):
        """Carrera entre validar y emitir la cookie: si el dueño cambia la
        contraseña mientras se rehashea, la cookie NO debe sellarse con la versión
        nueva (esta sesión validó con la vieja) y el rehasheo no debe revertir el
        cambio."""
        from zascarr.services.auth import hash_password, hash_password_async, sesion_valida

        viejo = _hash_con_iteraciones("vieja", 1000)
        nuevo = hash_password("nueva")
        get_settings().auth_password_hash = viejo
        get_settings().auth_session_version = 0

        real = hash_password_async

        async def espia(password):
            # El dueño guarda una contraseña nueva justo en el hueco del rehasheo.
            db_fake.fila.values = {
                **db_fake.fila.values,
                "auth_password_hash": nuevo, "auth_session_version": 1,
            }
            get_settings().auth_password_hash = nuevo
            get_settings().auth_session_version = 1
            return await real(password)

        monkeypatch.setattr("zascarr.web.auth.hash_password_async", espia)
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={"password": "vieja", "next": "/ui/"})

        assert r.status_code == 303
        # La cookie se selló con la versión con la que se VALIDÓ (0): no vale con
        # la versión vigente (1), así que esa sesión no resucita.
        cookie = r.cookies[COOKIE_NAME]
        assert sesion_valida(cookie, "clave-de-prueba", 0) is True
        assert sesion_valida(cookie, "clave-de-prueba", 1) is False
        # El hash nuevo del dueño sobrevive: el rehasheo no lo pisó.
        assert db_fake.fila.values["auth_password_hash"] == nuevo
