"""
tests/test_exposicion.py

A11 — exposición de red. Tres cosas que no pueden divergir:

1. Cómo se **calcula** hasta dónde llega la interfaz (`exposicion_efectiva`) y
   cuándo se **avisa** (`/api/health`): solo si está abierta y SIN contraseña.
2. Cómo se **publica** el puerto en `docker-compose.yml`: por defecto solo
   localhost, y **Postgres y Redis nunca** salen de ahí (ADR 0004).
3. Que las dos copias del mínimo de contraseña (Python y bash) sean la misma.
"""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import seguridad
from zascarr.services.seguridad import (
    EXPOSICION_LOCAL,
    EXPOSICION_PROXY,
    EXPOSICION_RED,
    aviso_de_exposicion,
    exposicion_efectiva,
    hay_contrasena,
)

RAIZ = Path(__file__).resolve().parents[1]


def _ajustes(bind="127.0.0.1", base_url="", modo="none", hash_="") -> SimpleNamespace:
    return SimpleNamespace(
        zascarr_bind_address=bind, base_url=base_url, auth_mode=modo, auth_password_hash=hash_,
    )


class TestExposicionEfectiva:

    @pytest.mark.parametrize("bind", ["127.0.0.1", "localhost", "::1", "[::1]", " 127.0.0.1 ", "LOCALHOST"])
    def test_bind_local_es_local(self, bind):
        assert exposicion_efectiva(_ajustes(bind=bind)) == EXPOSICION_LOCAL

    @pytest.mark.parametrize("bind", ["0.0.0.0", "192.168.1.50", "::", "10.0.0.7", "raspberrypi.local"])
    def test_cualquier_otro_bind_es_red(self, bind):
        assert exposicion_efectiva(_ajustes(bind=bind)) == EXPOSICION_RED

    def test_un_bind_vacio_no_se_toma_por_local(self):
        """Fallar hacia el lado que avisa: un valor ilegible no puede aparentar «solo localhost»."""
        assert exposicion_efectiva(_ajustes(bind="")) == EXPOSICION_RED

    def test_base_url_publica_con_bind_local_es_proxy(self):
        s = _ajustes(base_url="https://tebeos.ejemplo.org")
        assert exposicion_efectiva(s) == EXPOSICION_PROXY

    @pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000", ""])
    def test_base_url_local_o_vacia_sigue_siendo_local(self, url):
        assert exposicion_efectiva(_ajustes(base_url=url)) == EXPOSICION_LOCAL

    def test_el_bind_abierto_manda_sobre_la_base_url(self):
        s = _ajustes(bind="0.0.0.0", base_url="https://tebeos.ejemplo.org")
        assert exposicion_efectiva(s) == EXPOSICION_RED


class TestHayContrasena:

    def test_modo_ninguno_no(self):
        assert not hay_contrasena(_ajustes(modo="none", hash_="pbkdf2…"))

    def test_modo_con_contrasena_pero_sin_hash_no(self):
        assert not hay_contrasena(_ajustes(modo="password"))

    @pytest.mark.parametrize("modo", ["password", "user_password"])
    def test_modo_con_hash_si(self, modo):
        assert hay_contrasena(_ajustes(modo=modo, hash_="pbkdf2…"))


class TestAvisoDeExposicion:

    def test_local_sin_contrasena_no_avisa(self):
        """El caso por defecto: nada que decir. Un aviso permanente enseñaría a ignorarlos."""
        assert aviso_de_exposicion(_ajustes()) is None

    def test_red_sin_contrasena_avisa(self):
        aviso = aviso_de_exposicion(_ajustes(bind="0.0.0.0"))
        assert aviso and "red local" in aviso and "Ajustes" in aviso

    def test_proxy_sin_contrasena_avisa_y_no_enseña_la_url(self):
        aviso = aviso_de_exposicion(_ajustes(base_url="https://secreto.ejemplo.org"))
        assert aviso and "pública" in aviso
        assert "secreto.ejemplo.org" not in aviso

    @pytest.mark.parametrize("ajustes", [
        _ajustes(bind="0.0.0.0", modo="password", hash_="pbkdf2…"),
        _ajustes(base_url="https://a.org", modo="user_password", hash_="pbkdf2…"),
    ])
    def test_expuesta_con_contrasena_no_avisa(self, ajustes):
        assert aviso_de_exposicion(ajustes) is None


class FakeSession:
    async def execute(self, _statement):
        return None


def _salud(monkeypatch, bind="127.0.0.1", base_url="", modo="none", hash_=""):
    """GET /api/health con la BD y los servicios opcionales simulados, sobre una
    copia REAL de `Settings` (el endpoint usa muchos campos más que estos)."""
    ajustes = get_settings().model_copy(update={
        "zascarr_bind_address": bind, "base_url": base_url,
        "auth_mode": modo, "auth_password_hash": hash_,
    })
    monkeypatch.setattr("zascarr.api.health.get_settings", lambda: ajustes)

    async def _get_db():
        yield FakeSession()

    app.dependency_overrides[get_db] = _get_db
    try:
        with patch("zascarr.api.health._check_transmission", AsyncMock(return_value=True)), \
             patch("zascarr.api.health._check_amule", AsyncMock(return_value=True)), \
             patch("zascarr.api.health._database_status", AsyncMock(return_value=("ok", "ok"))):
            return TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestHealthAvisaDeExposicion:

    def test_por_defecto_no_hay_aviso_de_exposicion(self, monkeypatch):
        body = _salud(monkeypatch).json()
        assert "exposicion" not in body["warnings"]

    def test_abierta_a_la_red_sin_contrasena_avisa(self, monkeypatch):
        body = _salud(monkeypatch, bind="0.0.0.0").json()
        assert "red local" in body["warnings"]["exposicion"]

    def test_el_aviso_no_cambia_el_estado_global(self, monkeypatch):
        """Observacional, no bloqueante (CLAUDE.md §3.2): igual que una VPN caída."""
        body = _salud(monkeypatch, bind="0.0.0.0").json()
        assert body["status"] == "healthy"

    def test_abierta_con_contrasena_no_avisa(self, monkeypatch):
        body = _salud(monkeypatch, bind="0.0.0.0", modo="password", hash_="pbkdf2…").json()
        assert "exposicion" not in body["warnings"]


class TestComposePublicaElPuerto:
    """El puerto de la aplicación es configurable; los de Postgres y Redis, jamás."""

    @staticmethod
    def _puertos() -> dict[str, list[str]]:
        compose = (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")
        servicios: dict[str, list[str]] = {}
        actual = None
        for linea in compose.splitlines():
            m = re.match(r"^  ([a-z]+):\s*$", linea)
            if m:
                actual = m.group(1)
                servicios[actual] = []
            elif actual and (p := re.match(r'^\s+- "([^"]*:\d+)"\s*$', linea)):
                servicios[actual].append(p.group(1))
        return servicios

    def test_postgres_y_redis_siguen_fijos_en_localhost(self):
        puertos = self._puertos()
        assert puertos["postgres"] == ["127.0.0.1:5432:5432"]
        assert puertos["redis"] == ["127.0.0.1:6379:6379"]

    def test_la_app_usa_la_variable_con_localhost_por_defecto(self):
        assert self._puertos()["zascarr"] == ["${ZASCARR_BIND_ADDRESS:-127.0.0.1}:8000:8000"]

    def test_nadie_publica_en_todas_las_interfaces_por_defecto(self):
        """Ningún puerto del compose queda en `0.0.0.0` ni sin dirección explícita."""
        for servicio, puertos in self._puertos().items():
            for p in puertos:
                assert p.startswith(("127.0.0.1:", "${ZASCARR_BIND_ADDRESS:-127.0.0.1}:")), (servicio, p)


class TestMinimoDeContrasenaIgualEnBash:
    """`scripts/_exposicion.sh` repite el mínimo para no fallar tarde en el
    instalador. Si divergen, el instalador aceptaría (o rechazaría) lo que la app
    dice lo contrario."""

    def test_longitud_minima_igual(self):
        sh = (RAIZ / "scripts" / "_exposicion.sh").read_text(encoding="utf-8")
        m = re.search(r"^LONGITUD_MINIMA_CONTRASENA=(\d+)\s*$", sh, re.M)
        assert m, "falta LONGITUD_MINIMA_CONTRASENA en scripts/_exposicion.sh"
        assert int(m.group(1)) == seguridad.LONGITUD_MINIMA
