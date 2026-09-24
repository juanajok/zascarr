"""
tests/test_health.py

Suite de /api/health. Objetivo principal: regresión del hallazgo E2E
release 1.0 — TransmissionClient/AMuleClient se llamaban secuencialmente
con timeout=30.0 cada uno; si ninguno respondía con RST inmediato (VPN aún
no arriba, servicio parado, firewall con DROP en vez de REJECT — nada raro
en una Pi real), /api/health tardaba hasta ~60s, y el HEALTHCHECK del
Dockerfile (--timeout=10s) marcaba el contenedor unhealthy de forma casi
permanente. Ahora corren en paralelo con un timeout corto propio.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app


class FakeSession:
    async def execute(self, _statement):
        return None


def _fake_db_client():
    async def _get_db():
        yield FakeSession()

    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _get_db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)

    return _Ctx()


async def _cuelga(segundos: float) -> bool:
    await asyncio.sleep(segundos)
    return True


class TestHealthLatenciaAcotada:

    def test_transmission_y_amule_se_consultan_en_paralelo_no_en_serie(self):
        """Con el bug original (llamadas secuenciales), dos comprobaciones
        de 0.2s habrían tardado >= 0.4s. En paralelo deben tardar ~0.2s."""
        with patch(
            "zascarr.api.health._check_transmission", lambda: _cuelga(0.2)
        ), patch("zascarr.api.health._check_amule", lambda: _cuelga(0.2)):
            with _fake_db_client() as client:
                t0 = time.monotonic()
                r = client.get("/api/health")
                elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed < 0.35, f"tardó {elapsed:.2f}s — ¿volvió a ser secuencial?"

    def test_servicio_que_no_responde_no_bloquea_mas_del_timeout_corto(self):
        """Un servicio que nunca responde (el caso real: firewall con DROP)
        no debe colgar /api/health más allá de su timeout interno corto,
        muy por debajo de los 30s del cliente HTTP subyacente."""
        with patch(
            "zascarr.api.health._check_transmission", lambda: _cuelga(999)
        ), patch("zascarr.api.health._check_amule", lambda: _cuelga(999)):
            with _fake_db_client() as client:
                t0 = time.monotonic()
                r = client.get("/api/health")
                elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed < 5.0
        body = r.json()
        assert body["checks"]["transmission"] == "unreachable"
        assert body["checks"]["amule"] == "unreachable"

    def test_status_degraded_cuando_solo_falla_lo_opcional(self):
        with patch(
            "zascarr.api.health._check_transmission", AsyncMock(return_value=True)
        ), patch(
            "zascarr.api.health._check_amule", AsyncMock(return_value=False)
        ):
            with _fake_db_client() as client:
                r = client.get("/api/health")

        assert r.status_code == 200
        body = r.json()
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["transmission"] == "ok"
        assert body["checks"]["amule"] == "unreachable"
        assert body["status"] == "degraded"
