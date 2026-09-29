"""D8 — la migración 0015 deja `origen='manual'` y `numero` NULL en los items que
ya existían.

Lo que lo garantiza es el **`server_default` de la columna**, no un `UPDATE`: en
PostgreSQL, `ADD COLUMN ... NOT NULL DEFAULT 'manual'` ya rellena las filas
existentes. Por eso la prueba **siembra filas antes de subir la migración** en
vez de comprobar un `UPDATE` que no tocaría nada — y proteger el backfill importa
porque es lo que impide que la retirada de items de política toque lo que pidió
el coleccionista.

Se salta sin `TEST_DATABASE_URL`, mismo patrón que el resto de tests de Postgres.

    docker run --rm -d --name zascarr-pg-test -e POSTGRES_USER=test \\
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=zascarr_test -p 127.0.0.1:55432:5432 postgres:15
    TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55432/zascarr_test \\
        pytest tests/test_migracion_d8_pg.py
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

RAIZ = Path(__file__).resolve().parents[1]


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _alembic(*args: str, estricto: bool = True) -> None:
    """Ejecuta alembic contra la BD de pruebas.

    `PYTHONSAFEPATH=1` a propósito: sin él, el directorio `alembic/` del repo
    sombrea el paquete instalado al lanzar `python -m alembic` desde la raíz."""
    entorno = dict(os.environ)
    entorno["DATABASE_URL"] = _url_asyncpg(TEST_DATABASE_URL or "")
    entorno["PYTHONSAFEPATH"] = "1"
    resultado = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=RAIZ, env=entorno, capture_output=True, text=True, timeout=180,
    )
    if estricto:
        assert resultado.returncode == 0, resultado.stderr[-2000:]


@pytest.mark.asyncio
async def test_los_items_que_ya_existian_quedan_manual_y_sin_numero():
    motor = create_async_engine(_url_asyncpg(TEST_DATABASE_URL or ""))
    serie_id, item_id = uuid4(), uuid4()
    # Si algo falla a mitad, la BD de pruebas tiene que quedar al día: si no,
    # todos los tests siguientes fallarían por un esquema viejo.
    _alembic("downgrade", "0014")
    try:
        async with motor.begin() as conexion:
            await conexion.execute(
                text("INSERT INTO series (id, title) VALUES (:s, 'Serie previa a D8')"),
                {"s": serie_id})
            await conexion.execute(
                text("INSERT INTO wishlist (id, series_id, status) VALUES (:i, :s, 'wanted')"),
                {"i": item_id, "s": serie_id})

        _alembic("upgrade", "head")

        async with motor.begin() as conexion:
            fila = (await conexion.execute(
                text("SELECT origen, numero FROM wishlist WHERE id = :i"),
                {"i": item_id})).one()
        assert fila.origen == "manual", (
            "un item que ya existía tiene que quedar como manual: la retirada de "
            "items de política no puede tocar lo que pidió el coleccionista")
        assert fila.numero is None, "el backfill no inventa números"
    finally:
        async with motor.begin() as conexion:
            await conexion.execute(text("DELETE FROM wishlist WHERE id = :i"), {"i": item_id})
            await conexion.execute(text("DELETE FROM series WHERE id = :s"), {"s": serie_id})
        _alembic("upgrade", "head", estricto=False)
        await motor.dispose()
