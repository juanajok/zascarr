"""tests/test_auth_limites.py

Retraso progresivo por IP, caché de aciertos de Basic y tope de cola (ficha de
seguridad, paso 2). El retraso y la caché son estado de módulo: el conftest lo
limpia entre tests.
"""
from __future__ import annotations

import asyncio
import base64
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import auth as auth_mod
from zascarr.services.auth import (
    ColaDeVerificacionLlenaError,
    hash_password,
    intentar_credenciales,
    ip_de_peticion,
    limpiar_cache_basic,
    limpiar_fallos,
)


class _FakeSession:
    def __init__(self):
        from zascarr.models import RuntimeSetting
        self.fila = RuntimeSetting(id=1, values={})

    async def execute(self, _statement):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self.fila)
        return result

    def add(self, obj):
        self.fila = obj

    async def flush(self):
        return None


@pytest.fixture
def restaurar_settings():
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    originales = {campo: getattr(s, campo) for campo in _ALL_FIELDS}
    yield
    for campo, valor in originales.items():
        setattr(s, campo, valor)


@pytest.fixture
def db_fake():
    return _FakeSession()


@pytest.fixture(autouse=True)
def _db_override(db_fake):
    async def _get_db():
        yield db_fake
    app.dependency_overrides[get_db] = _get_db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def settings_password(restaurar_settings):
    s = get_settings()
    s.auth_mode = "password"
    s.auth_password_hash = hash_password("secreta")
    s.secret_key = "clave-de-prueba"
    s.auth_session_version = 0
    return s


@pytest.fixture
def retraso_rapido(monkeypatch):
    """Retrasos diminutos para no ralentizar la suite."""
    monkeypatch.setattr("zascarr.services.auth._RETRASO_BASE", 0.05)
    monkeypatch.setattr("zascarr.services.auth._RETRASO_MAX", 0.2)


def _cabecera(usuario: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{usuario}:{password}".encode()).decode()


def _app_minima():
    """App mínima con el middleware real y una ruta `/api/*` que no toca BD."""
    from fastapi import FastAPI

    from zascarr.services.auth import AuthMiddleware
    mini = FastAPI()
    mini.add_middleware(AuthMiddleware)

    @mini.get("/api/algo")
    def _api_algo():
        return {"ok": True}

    return mini


# ── Retraso progresivo ───────────────────────────────────────────────────────

class TestRetrasoProgresivo:

    def test_crece_y_tiene_tope(self, retraso_rapido):
        limpiar_fallos()
        ip = "10.0.0.1"
        assert auth_mod._retraso_actual(ip) == 0.0
        auth_mod._anotar_fallo(ip)
        assert auth_mod._retraso_actual(ip) == pytest.approx(0.05)
        auth_mod._anotar_fallo(ip)
        assert auth_mod._retraso_actual(ip) == pytest.approx(0.1)
        for _ in range(20):
            auth_mod._anotar_fallo(ip)
        assert auth_mod._retraso_actual(ip) == pytest.approx(0.2)   # tope

    def test_los_fallos_caducan(self, monkeypatch):
        limpiar_fallos()
        monkeypatch.setattr("zascarr.services.auth._VENTANA_FALLOS", 0)
        auth_mod._anotar_fallo("10.0.0.9")
        assert auth_mod._retraso_actual("10.0.0.9") == 0.0

    @pytest.mark.asyncio
    async def test_la_espera_no_bloquea_el_bucle(self, retraso_rapido):
        """`asyncio.sleep`, no `time.sleep`: otras peticiones siguen atendidas."""
        limpiar_fallos()
        auth_mod._anotar_fallo("10.0.0.2")
        corrio = []

        async def otra():
            corrio.append(True)

        tarea = asyncio.create_task(otra())
        await auth_mod.esperar_retraso("10.0.0.2")
        assert corrio == [True]
        await tarea

    @pytest.mark.asyncio
    async def test_tras_los_fallos_la_credencial_correcta_entra(
            self, settings_password, retraso_rapido):
        limpiar_fallos()
        ip = "10.0.0.3"
        for _ in range(3):
            assert await intentar_credenciales(ip, "", "mala", settings_password) is False
        # La correcta entra (tras el retraso) y limpia el contador.
        assert await intentar_credenciales(ip, "", "secreta", settings_password) is True
        assert auth_mod._retraso_actual(ip) == 0.0

    def test_login_correcto_tras_fallos_entra(self, settings_password, retraso_rapido):
        client = TestClient(app, follow_redirects=False)
        for _ in range(3):
            client.post("/login", data={"password": "mala", "next": "/ui/"})

        r = client.post("/login", data={"password": "secreta", "next": "/ui/"})

        assert r.status_code == 303


# ── Tope de cola (429) ───────────────────────────────────────────────────────

class TestTopeDeCola:

    @pytest.mark.asyncio
    async def test_sin_hueco_lanza_cola_llena(self, monkeypatch, settings_password):
        monkeypatch.setattr("zascarr.services.auth._ESPERA_MAX_COLA", 0.01)
        limpiar_fallos()
        # Ocupa los dos huecos del semáforo.
        await auth_mod._pbkdf2_sem.acquire()
        await auth_mod._pbkdf2_sem.acquire()
        try:
            with pytest.raises(ColaDeVerificacionLlenaError):
                await auth_mod.verify_password("secreta", settings_password.auth_password_hash)
        finally:
            auth_mod._pbkdf2_sem.release()
            auth_mod._pbkdf2_sem.release()

    @pytest.mark.asyncio
    async def test_el_429_no_cuenta_como_fallo(self, monkeypatch, settings_password):
        async def _sin_hueco(*_args, **_kwargs):
            raise ColaDeVerificacionLlenaError

        monkeypatch.setattr("zascarr.services.auth._en_ejecutor_pbkdf2", _sin_hueco)
        limpiar_fallos()
        ip = "10.0.0.4"

        with pytest.raises(ColaDeVerificacionLlenaError):
            await intentar_credenciales(ip, "", "secreta", settings_password)

        assert auth_mod._retraso_actual(ip) == 0.0

    def test_login_con_cola_llena_da_429(self, monkeypatch, settings_password):
        async def _sin_hueco(*_args, **_kwargs):
            raise ColaDeVerificacionLlenaError

        monkeypatch.setattr("zascarr.services.auth._en_ejecutor_pbkdf2", _sin_hueco)
        client = TestClient(app, follow_redirects=False)

        r = client.post("/login", data={"password": "secreta", "next": "/ui/"})

        assert r.status_code == 429
        assert "Demasiados" in r.text

    def test_basic_con_cola_llena_da_429(self, monkeypatch, settings_password):
        async def _sin_hueco(*_args, **_kwargs):
            raise ColaDeVerificacionLlenaError

        monkeypatch.setattr("zascarr.services.auth._en_ejecutor_pbkdf2", _sin_hueco)
        client = TestClient(_app_minima(), follow_redirects=False)

        r = client.get("/api/algo", headers={"Authorization": _cabecera("", "secreta")})

        assert r.status_code == 429
        assert r.headers.get("retry-after") == "5"


# ── Caché de aciertos de Basic ───────────────────────────────────────────────

class TestCacheBasic:

    def test_solo_aciertos_y_por_version(self):
        limpiar_cache_basic()
        cab = _cabecera("", "secreta")
        assert auth_mod._acierto_cache_basic("s", cab, 0) is False
        auth_mod._guardar_cache_basic("s", cab, 0)
        assert auth_mod._acierto_cache_basic("s", cab, 0) is True
        assert auth_mod._acierto_cache_basic("s", cab, 1) is False        # otra versión
        assert auth_mod._acierto_cache_basic("otro-secreto", cab, 0) is False

    def test_caduca(self, monkeypatch):
        limpiar_cache_basic()
        monkeypatch.setattr("zascarr.services.auth._CACHE_BASIC_TTL", -1)
        auth_mod._guardar_cache_basic("s", "cab", 0)
        assert auth_mod._acierto_cache_basic("s", "cab", 0) is False

    def test_esta_acotada(self, monkeypatch):
        limpiar_cache_basic()
        monkeypatch.setattr("zascarr.services.auth._CACHE_BASIC_MAX", 4)
        for i in range(20):
            auth_mod._guardar_cache_basic("s", f"cab-{i}", 0)
        assert len(auth_mod._cache_basic) <= 4

    def test_un_fallo_no_se_cachea(self, settings_password):
        limpiar_cache_basic()
        client = TestClient(_app_minima(), follow_redirects=False)

        r = client.get("/api/algo", headers={"Authorization": _cabecera("", "mala")})

        assert r.status_code == 401
        assert auth_mod._cache_basic == {}

    def test_un_acierto_evita_repetir_pbkdf2(self, settings_password, monkeypatch):
        limpiar_cache_basic()
        llamadas = []
        real = auth_mod.verify_password

        async def espia(password, stored):
            llamadas.append(True)
            return await real(password, stored)

        monkeypatch.setattr("zascarr.services.auth.verify_password", espia)
        client = TestClient(_app_minima())
        cab = {"Authorization": _cabecera("", "secreta")}

        assert client.get("/api/algo", headers=cab).status_code == 200
        assert client.get("/api/algo", headers=cab).status_code == 200

        assert len(llamadas) == 1   # la segunda salió de la caché


# ── Cliente detrás de proxy ──────────────────────────────────────────────────

def _peticion_falsa(host: str, xff: str | None = None):
    from starlette.requests import Request
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http", "method": "GET", "path": "/login", "headers": headers,
        "client": (host, 12345), "query_string": b"", "scheme": "http",
        "server": ("localhost", 8000),
    }
    return Request(scope)


class TestIpDetrasDeProxy:

    def test_sin_proxy_de_confianza_se_ignora_x_forwarded_for(self, restaurar_settings):
        s = get_settings()
        s.trusted_proxy = False
        peticion = _peticion_falsa("1.2.3.4", "9.9.9.9")
        assert ip_de_peticion(peticion, s) == "1.2.3.4"

    def test_con_proxy_de_confianza_se_usa_x_forwarded_for(self, restaurar_settings):
        s = get_settings()
        s.trusted_proxy = True
        peticion = _peticion_falsa("1.2.3.4", "9.9.9.9, 8.8.8.8")
        assert ip_de_peticion(peticion, s) == "9.9.9.9"

    @pytest.mark.asyncio
    async def test_el_atacante_no_penaliza_al_dueno_mas_alla_del_retraso(
            self, settings_password, retraso_rapido):
        """Sin proxy de confianza todos comparten IP: el atacante solo puede
        añadir retraso (progresivo y con tope), nunca bloquear. El dueño entra
        tras la espera máxima."""
        limpiar_fallos()
        ip = "10.0.0.5"
        for _ in range(50):
            auth_mod._anotar_fallo(ip)

        assert auth_mod._retraso_actual(ip) == pytest.approx(auth_mod._RETRASO_MAX)
        assert await intentar_credenciales(ip, "", "secreta", settings_password) is True
        assert auth_mod._retraso_actual(ip) == 0.0
