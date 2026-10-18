# ruff: noqa: E501
"""La aplicación se niega a servir con una contraseña de base de datos conocida (última barrera).

El instalador genera una propia y Compose rechaza las de ejemplo; esto cubre la ruta que no pasa por ninguno de los dos
(`DATABASE_URL` copiado de un ejemplo). Falla CERRADO: arranca en modo solo diagnóstico, sin abrir ninguna conexión, y el
motivo queda en el log sin el valor.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url

from tests._tabla_credenciales import TABLA
from zascarr.main import app
from zascarr.utils.credenciales import es_credencial_conocida, problema_de_credenciales

REAL = "postgresql+asyncpg://comics_admin:Sint3tica-App-0007@postgres:5432/zascarr"


@pytest.mark.parametrize("valor,conocida", [
    ("cambia_esto_ahora", True), ("SuperSecretPassword123", True), ("CHANGEME", True), ("", True), (None, True),
    ('"cambia_esto_ahora"', True), ("Sint3tica-App-0007", False), ("cambia_esto_ahora_no", False),
])
def test_es_credencial_conocida(valor, conocida):
    assert es_credencial_conocida(valor) is conocida


@pytest.mark.parametrize("valor,no_vale", TABLA, ids=[repr(v)[:30] for v, _ in TABLA])
def test_la_regla_unica_de_las_tres_implementaciones(valor, no_vale):
    """Misma tabla que Bash (test_credenciales_lib) y el servicio de Compose (test_compose_credenciales)."""
    assert es_credencial_conocida(valor) is no_vale


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://comics_admin:SuperSecretPassword123@postgres:5432/zascarr",
    "postgresql+asyncpg://comics_admin:cambia_esto_ahora@postgres:5432/zascarr",
    "postgresql+asyncpg://comics_admin:changeme@postgres:5432/zascarr",
    "postgresql+asyncpg://comics_admin@postgres:5432/zascarr",              # sin contraseña, base remota
    "postgresql+asyncpg://comics_admin:@db.ejemplo.org:5432/zascarr",
    "postgresql+asyncpg://INVALID:INVALID@127.0.0.1:5432/INVALID",          # el relleno de config.py
    "esto no es una url",
])
def test_problema_de_credenciales_detecta_lo_no_seguro(url):
    assert problema_de_credenciales(url)


@pytest.mark.parametrize("url", [REAL, "postgresql://test:test@localhost:5432/zascarr_test"])
def test_problema_de_credenciales_deja_pasar_lo_legitimo(url):
    assert problema_de_credenciales(url) is None


# Autenticación alternativa soportada, explícita (ADR 0012): SOLO el socket Unix local (sin host: `peer`/`trust` del
# propio equipo, p. ej. `postgresql+asyncpg://usuario@/base?host=/var/run/postgresql`). Una conexión TCP sin contraseña
# —ni siquiera al bucle local— no es autenticación alternativa: cualquier proceso del equipo podría usarla.
@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://comics_admin@/zascarr?host=/var/run/postgresql",
    "postgresql+asyncpg://comics_admin@/zascarr",
])
def test_el_socket_unix_sin_contrasena_es_la_unica_alternativa_soportada(url):
    assert problema_de_credenciales(url) is None


@pytest.mark.parametrize("url", [
    "postgresql://postgres@localhost/zascarr_test",
    "postgresql+asyncpg://comics_admin@127.0.0.1:5432/zascarr",
    "postgresql+asyncpg://comics_admin:@[::1]:5432/zascarr",
    "postgresql+asyncpg://comics_admin@postgres:5432/zascarr",
])
def test_una_conexion_tcp_sin_contrasena_no_es_una_alternativa_ni_en_local(url):
    motivo = problema_de_credenciales(url)
    assert motivo and "contraseña" in motivo


def test_el_motivo_no_lleva_el_valor():
    url = "postgresql+asyncpg://comics_admin:SuperSecretPassword123@postgres:5432/zascarr"
    assert "SuperSecretPassword123" not in (problema_de_credenciales(url) or "")


def test_el_arranque_con_una_contrasena_conocida_no_abre_ninguna_conexion(monkeypatch, caplog):
    """Falla cerrado: modo diagnóstico, y el motor ni se toca."""
    from zascarr import database

    intentos = []

    class MotorQueNoDebeUsarse:
        url = make_url("postgresql+asyncpg://comics_admin:SuperSecretPassword123@postgres:5432/zascarr")

        def begin(self):
            intentos.append(1)               # el lifespan se traga las excepciones: hay que anotar el intento
            raise AssertionError("se intentó abrir una conexión con una credencial conocida")

        async def dispose(self):
            return None

    monkeypatch.setattr(database, "engine", MotorQueNoDebeUsarse())
    with TestClient(app) as cliente:
        assert app.state.db_degraded is True
        assert cliente.get("/api/health").status_code in (200, 503)
    assert intentos == [], "abrió una conexión con una credencial conocida"


def test_con_una_url_legitima_el_arranque_si_intenta_conectar(monkeypatch):
    from zascarr import database

    intentos = []

    class Motor:
        url = make_url(REAL)

        def begin(self):
            intentos.append(1)
            raise ConnectionError("sin base de datos en esta prueba")

        async def dispose(self):
            return None

    monkeypatch.setattr(database, "engine", Motor())
    with TestClient(app):
        assert intentos, "con una URL legítima debía intentar conectar"
