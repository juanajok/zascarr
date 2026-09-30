"""conftest.py — Configuración de pytest para ZascArr."""
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "sin_origen: el test controla Host/Origin a mano (middleware de seguridad)",
    )


@pytest.fixture(autouse=True)
def _limpiar_estado_auth():
    """El retraso progresivo y la caché de Basic son estado de módulo: se limpian
    entre tests para que no se filtren (ni ralenticen la suite)."""
    from zascarr.services.auth import limpiar_cache_basic, limpiar_fallos
    limpiar_fallos()
    limpiar_cache_basic()
    yield
    limpiar_fallos()
    limpiar_cache_basic()


@pytest.fixture(autouse=True)
def _testclient_en_localhost(monkeypatch, request):
    """Por defecto, `TestClient` usa `base_url="http://localhost"` y envía
    `Origin: http://localhost`: así `Host` y `Origin` pasan la comprobación de
    Origen/Host del middleware de seguridad sin tocar cada prueba a mano.

    Las pruebas del propio middleware se marcan `@pytest.mark.sin_origen` para
    saltarse esto y mandar cabeceras a mano (sin Origin, `Origin: null`, Host
    ajeno…) esperando el 403."""
    if request.node.get_closest_marker("sin_origen"):
        return

    from fastapi.testclient import TestClient
    original = TestClient.__init__

    def _init(self, app, *args, **kwargs):
        kwargs.setdefault("base_url", "http://localhost")
        cabeceras = dict(kwargs.get("headers") or {})
        cabeceras.setdefault("Origin", "http://localhost")
        kwargs["headers"] = cabeceras
        original(self, app, *args, **kwargs)

    monkeypatch.setattr(TestClient, "__init__", _init)
