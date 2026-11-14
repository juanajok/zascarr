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
def _limpiar_cortesia():
    """El limitador compartido es estado de módulo: se reinicia entre pruebas para que una espera
    no se filtre de un test a otro (y para que la suite no duerma de verdad)."""
    from zascarr.utils.cortesia import reiniciar_para_pruebas
    reiniciar_para_pruebas()
    yield
    reiniciar_para_pruebas()


@pytest.fixture(autouse=True)
def _limpiar_cache_gcd():
    """La caché de búsquedas GCD es estado de módulo: no debe filtrarse entre tests."""
    from zascarr.services.gcd import limpiar_cache_busquedas
    limpiar_cache_busquedas()
    yield
    limpiar_cache_busquedas()


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
    from zascarr.services.reautenticacion import reiniciar_estado as reiniciar_reauth
    limpiar_fallos()
    limpiar_cache_basic()
    reiniciar_estado_concurrencia()
    reiniciar_reauth()
    yield
    limpiar_fallos()
    limpiar_cache_basic()
    reiniciar_estado_concurrencia()
    reiniciar_reauth()


@pytest.fixture(autouse=True)
def _cerrojo_de_pruebas(monkeypatch, tmp_path_factory):
    """El cerrojo único de operaciones (BL-OPS1) vive en /run en producción y solo admite otra ruta con
    `ZASCARR_PRUEBAS=1` + `OPS_LOCK_FILE`. Sin esto, las pruebas que ejecutan los scripts reales (sin ser
    root) no podrían tomarlo; cada prueba tiene el suyo, en una carpeta aparte (no ensucia `tmp_path`).
    Las pruebas del propio cerrojo lo redefinen o lo quitan."""
    monkeypatch.setenv("ZASCARR_PRUEBAS", "1")
    monkeypatch.setenv("OPS_LOCK_FILE", str(tmp_path_factory.mktemp("cerrojo") / "ops.lock"))


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


@pytest.fixture(autouse=True)
def _restauracion_reciente(tmp_path_factory, monkeypatch):
    """#334 B2: /api/health incluye la restauración de comprobación. Las pruebas
    que no son de restauración parten de una restauración reciente;
    `TestHealthRestore` sustituye el fichero por el caso que prueba.
    """
    import json
    import time

    from zascarr.config import get_settings

    ruta = tmp_path_factory.mktemp("restore-status") / "restore-status.json"
    ruta.write_text(
        json.dumps({"status": "ok", "error": None,
                    "last_ok_at_epoch": time.time()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(get_settings(), "restore_status_file", str(ruta))


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


@pytest.fixture(autouse=True)
def _guardian_compartidos_por_defecto(monkeypatch):
    """#488: las pruebas que ya existían no declaran fuentes de compartidos.

    El guardián real (fallo cerrado) se prueba en `test_compartidos.py` y en
    `test_tagger_compartido.py`, que lo sustituyen explícitamente. Para el resto
    de la suite, el tagger parte de «no compartido» para no cambiar su contrato.
    """
    from zascarr.services import tagger as tagger_mod
    from zascarr.services.compartidos import Decision, EstadoComparticion

    async def _no_compartido(path, **_kw):
        return Decision(EstadoComparticion.NO_COMPARTIDO, "pruebas")

    monkeypatch.setattr(tagger_mod, "estado_de_comparticion", _no_compartido)
