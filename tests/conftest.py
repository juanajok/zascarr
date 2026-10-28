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
    """El retraso progresivo, la caché de Basic y las primitivas de concurrencia
    (candado/semáforo) son estado de módulo: se limpian entre tests para que no
    se filtren, ni ralenticen la suite, ni queden atados a un bucle cerrado."""
    from zascarr.services.auth import (
        limpiar_cache_basic,
        limpiar_fallos,
        reiniciar_estado_concurrencia,
    )
    limpiar_fallos()
    limpiar_cache_basic()
    reiniciar_estado_concurrencia()
    yield
    limpiar_fallos()
    limpiar_cache_basic()
    reiniciar_estado_concurrencia()


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


@pytest.fixture(autouse=True)
def _backup_reciente(tmp_path_factory, monkeypatch):
    """#334: /api/health incluye la copia de seguridad. Sin fichero de estado,
    cualquier instalación sin timer quedaría en `degraded`; las pruebas que no
    son de backups parten de una copia reciente. `TestHealthBackup` sustituye
    el fichero por el caso que prueba.

    Va en un directorio propio (no en `tmp_path`): hay pruebas que comprueban
    que su `tmp_path` solo contiene lo que crearon ellas.
    """
    import json
    import time

    from zascarr.config import get_settings

    ruta = tmp_path_factory.mktemp("backup-status") / "status.json"
    ruta.write_text(
        json.dumps({"status": "ok", "error": None,
                    "last_success_at_epoch": time.time()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(get_settings(), "backup_status_file", str(ruta))


@pytest.fixture(scope="session")
def _bd_de_pruebas_al_dia():
    """La BD de `TEST_DATABASE_URL` se migra a `head` UNA vez por sesión.

    Antes cada prueba de Postgres daba por hecho un esquema que nadie preparaba: sobre una base
    vacía fallaban ~100 y sobre una migrada fallaba la que exigía lo contrario (ver `tests/_pg.py`).
    Idempotente: si ya está en `head`, `upgrade` no hace nada.
    """
    import os

    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        from tests._pg import migrar_a_head
        migrar_a_head(url)


@pytest.fixture(autouse=True)
def _esquema_de_pruebas(request):
    import os

    if os.environ.get("TEST_DATABASE_URL"):
        request.getfixturevalue("_bd_de_pruebas_al_dia")
