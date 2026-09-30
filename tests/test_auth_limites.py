"""tests/test_auth_limites.py

Retraso progresivo por cuenta, serialización de intentos, caché de aciertos de
Basic y tope de cola (ficha de seguridad, paso 2). El retraso y la caché son
estado de módulo: el conftest lo limpia entre tests.
"""
from __future__ import annotations

import asyncio
import base64
import time
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


# ── Retraso progresivo (contador de la cuenta, no de la IP) ──────────────────

class TestRetrasoProgresivo:

    def test_crece_y_tiene_tope(self, retraso_rapido):
        limpiar_fallos()
        assert auth_mod._retraso_actual() == 0.0
        auth_mod._anotar_fallo()
        assert auth_mod._retraso_actual() == pytest.approx(0.05)
        auth_mod._anotar_fallo()
        assert auth_mod._retraso_actual() == pytest.approx(0.1)
        for _ in range(20):
            auth_mod._anotar_fallo()
        assert auth_mod._retraso_actual() == pytest.approx(0.2)   # tope

    def test_el_contador_es_la_cuenta_no_la_ip(self):
        """OWASP: el contador va por cuenta, no por IP de origen — rotar
        direcciones no lo esquiva (y no hay diccionario que crezca sin límite)."""
        import inspect
        firma = inspect.signature(intentar_credenciales)
        assert list(firma.parameters) == ["username", "password", "settings"]
        assert not hasattr(auth_mod, "ip_de_peticion")

    def test_los_fallos_caducan(self, monkeypatch):
        limpiar_fallos()
        monkeypatch.setattr("zascarr.services.auth._VENTANA_FALLOS", 0)
        auth_mod._anotar_fallo()
        assert auth_mod._retraso_actual() == 0.0

    @pytest.mark.asyncio
    async def test_la_espera_no_bloquea_el_bucle(self, retraso_rapido):
        """`asyncio.sleep`, no `time.sleep`: otras peticiones siguen atendidas."""
        limpiar_fallos()
        auth_mod._anotar_fallo()
        corrio = []

        async def otra():
            corrio.append(True)

        tarea = asyncio.create_task(otra())
        await auth_mod.esperar_retraso()
        assert corrio == [True]
        await tarea

    @pytest.mark.asyncio
    async def test_tras_los_fallos_la_credencial_correcta_entra(
            self, settings_password, retraso_rapido):
        limpiar_fallos()
        for _ in range(3):
            assert await intentar_credenciales("", "mala", settings_password) is False
        # La correcta entra (tras el retraso) y limpia el contador.
        assert await intentar_credenciales("", "secreta", settings_password) is True
        assert auth_mod._retraso_actual() == 0.0

    def test_login_correcto_tras_fallos_entra(self, settings_password, retraso_rapido):
        client = TestClient(app, follow_redirects=False)
        for _ in range(3):
            client.post("/login", data={"password": "mala", "next": "/ui/"})

        r = client.post("/login", data={"password": "secreta", "next": "/ui/"})

        assert r.status_code == 303


# ── Ráfaga en paralelo ───────────────────────────────────────────────────────

class TestRafagaParalela:

    @pytest.mark.asyncio
    async def test_diez_intentos_en_paralelo_se_serializan(self, settings_password, monkeypatch):
        """Sin candado, los diez leían el contador a la vez, ninguno esperaba y
        los diez iban a PBKDF2 (el límite real pasaba a ser el ejecutor)."""
        monkeypatch.setattr("zascarr.services.auth._RETRASO_BASE", 0.02)
        monkeypatch.setattr("zascarr.services.auth._RETRASO_MAX", 0.2)
        monkeypatch.setattr("zascarr.services.auth._INTENTOS_MAX_EN_COLA", 100)
        limpiar_fallos()
        a_la_vez = 0
        maximo = 0

        async def lenta(*_args, **_kwargs):
            nonlocal a_la_vez, maximo
            a_la_vez += 1
            maximo = max(maximo, a_la_vez)
            try:
                await asyncio.sleep(0.01)   # simula el coste de verificar
                return False
            finally:
                a_la_vez -= 1

        monkeypatch.setattr("zascarr.services.auth.credenciales_validas", lenta)

        inicio = time.monotonic()
        resultados = await asyncio.gather(*[
            intentar_credenciales("", "mala", settings_password) for _ in range(10)
        ])
        total = time.monotonic() - inicio

        assert resultados == [False] * 10
        assert maximo == 1                     # nunca dos verificaciones a la vez
        assert total >= 1.2                    # paga la suma de los retrasos

    @pytest.mark.asyncio
    async def test_la_cola_acotada_rechaza_sin_encolar_mas(self, settings_password, monkeypatch):
        monkeypatch.setattr("zascarr.services.auth._INTENTOS_MAX_EN_COLA", 3)
        monkeypatch.setattr("zascarr.services.auth._RETRASO_BASE", 0.1)
        limpiar_fallos()
        en_vuelo = 0
        maximo = 0

        async def lenta(*_args, **_kwargs):
            nonlocal en_vuelo, maximo
            en_vuelo += 1
            maximo = max(maximo, en_vuelo)
            try:
                await asyncio.sleep(0.5)
                return False
            finally:
                en_vuelo -= 1

        monkeypatch.setattr("zascarr.services.auth.credenciales_validas", lenta)

        resultados = await asyncio.gather(*[
            intentar_credenciales("", "mala", settings_password) for _ in range(10)
        ], return_exceptions=True)

        rechazos = [r for r in resultados if isinstance(r, ColaDeVerificacionLlenaError)]
        assert maximo <= 3                     # nunca más de los que caben
        assert len(rechazos) >= 5              # el resto no se encola: 429


# ── Tope de cola (429) y equilibrio del semáforo ─────────────────────────────

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
    async def test_equilibrio_tras_muchos_timeouts(self, monkeypatch, settings_password):
        """Tras muchos timeouts, los dos huecos del semáforo vuelven a estar
        disponibles. Cubre la cancelación normal de `asyncio.wait_for`; NO
        reproduce la carrera de que el permiso se adquiera justo al vencer el
        tiempo (queda como regresión, no como cierre de esa posibilidad)."""
        monkeypatch.setattr("zascarr.services.auth._ESPERA_MAX_COLA", 0.01)
        limpiar_fallos()
        await auth_mod._pbkdf2_sem.acquire()
        await auth_mod._pbkdf2_sem.acquire()
        try:
            for _ in range(20):
                with pytest.raises(ColaDeVerificacionLlenaError):
                    await auth_mod.verify_password(
                        "secreta", settings_password.auth_password_hash)
        finally:
            auth_mod._pbkdf2_sem.release()
            auth_mod._pbkdf2_sem.release()

        # Los dos huecos siguen ahí.
        await asyncio.wait_for(auth_mod._pbkdf2_sem.acquire(), timeout=0.1)
        await asyncio.wait_for(auth_mod._pbkdf2_sem.acquire(), timeout=0.1)
        auth_mod._pbkdf2_sem.release()
        auth_mod._pbkdf2_sem.release()

    @pytest.mark.asyncio
    async def test_el_429_no_cuenta_como_fallo(self, monkeypatch, settings_password):
        async def _sin_hueco(*_args, **_kwargs):
            raise ColaDeVerificacionLlenaError

        monkeypatch.setattr("zascarr.services.auth._en_ejecutor_pbkdf2", _sin_hueco)
        limpiar_fallos()

        with pytest.raises(ColaDeVerificacionLlenaError):
            await intentar_credenciales("", "secreta", settings_password)

        assert auth_mod._retraso_actual() == 0.0

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
