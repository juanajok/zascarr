"""E6 — con la BD no disponible, «solo diagnóstico» es literal.

Un arranque degradado sirve `/api/health` y falla cerrado en `/ui/*`, pero los
ciclos de fondo (auditoría, importación, enriquecimiento, orquestación) seguían
arrancando y fallarían cada intervalo sin poder hacer nada útil, llenando el log.
Aquí se fija que **no se arrancan**, y que el motivo se registra una vez.

No necesita Postgres: apunta a un puerto muerto, así que el arranque degradado se
provoca sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from structlog.testing import capture_logs

# Un puerto local cerrado: la conexión se rechaza al instante (no hay espera).
URL_MUERTA = "postgresql+asyncpg://test:test@127.0.0.1:1/no-existe"


def _sesion_muerta(monkeypatch):
    import zascarr.database as dbmod

    engine = create_async_engine(URL_MUERTA)
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "async_session_factory", sesion)


def test_bd_degradada_no_arranca_las_tareas_de_fondo(monkeypatch):
    from fastapi.testclient import TestClient

    from zascarr.main import app

    _sesion_muerta(monkeypatch)

    with capture_logs() as logs, TestClient(app, raise_server_exceptions=False) as client:
        r_health = client.get("/api/health")
        # Dentro del ciclo de vida: al apagar, E6 la restablece a False.
        degradado = app.state.db_degraded

    # El arranque es degradado de verdad (si no, la prueba no probaría nada).
    assert degradado is True
    assert r_health.status_code == 200
    fallo = r_health.json()["checks"]["database"]
    assert fallo in ("unreachable", "migration_required"), fallo

    assert any(
        log.get("event") == "background_tasks_skipped_db_degraded" for log in logs
    ), "no se registró que se saltaron las tareas de fondo"


def test_bd_disponible_si_arranca_las_tareas_de_fondo(monkeypatch):
    """La contraprueba: sin degradar, el aviso NO aparece (si apareciera siempre,
    la guarda sería un adorno). Necesita una BD migrada de verdad."""
    import os

    import pytest
    from fastapi.testclient import TestClient

    import zascarr.database as dbmod
    from zascarr.main import app

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("requiere TEST_DATABASE_URL para un arranque NO degradado")

    engine = create_async_engine(url.replace("postgresql://", "postgresql+asyncpg://"))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "engine", engine)
    monkeypatch.setattr(dbmod, "async_session_factory", sesion)

    with capture_logs() as logs, TestClient(app, raise_server_exceptions=False):
        assert app.state.db_degraded is False

    assert not any(
        log.get("event") == "background_tasks_skipped_db_degraded" for log in logs
    ), "se saltaron las tareas de fondo con la BD disponible"
