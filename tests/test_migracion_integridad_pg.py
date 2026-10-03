"""Integridad — la migración 0016 deja `original_sha256 = NULL` en las filas que
ya existían.

El hash original de un fichero ya etiquetado antes de este cambio **se perdió**
y no se puede reconstruir: se deja NULL y se dice, no se inventa. La prueba
siembra una fila ANTES de subir la 0016 y comprueba que queda NULL con el resto
de columnas intactas (mismo patrón que `tests/test_migracion_d8_pg.py`).

Se salta sin `TEST_DATABASE_URL`.

    docker run --rm -d --name zascarr-pg-test -e POSTGRES_USER=test \\
        -e POSTGRES_PASSWORD=test -e POSTGRES_DB=zascarr_test \\
        -p 127.0.0.1:55432:5432 postgres:15
    TEST_DATABASE_URL=postgresql://test:test@127.0.0.1:55432/zascarr_test \\
        pytest tests/test_migracion_integridad_pg.py
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _alembic(*args: str, estricto: bool = True) -> None:
    """Ejecuta alembic contra la BD de pruebas (entorno saneado: ver `tests/_pg.py`)."""
    alembic(TEST_DATABASE_URL or "", *args, estricto=estricto)


@pytest.mark.asyncio
async def test_las_filas_que_ya_existian_quedan_con_original_sha256_null():
    motor = create_async_engine(_url_asyncpg(TEST_DATABASE_URL or ""))
    file_id = uuid4()
    _alembic("downgrade", "0015")
    try:
        async with motor.begin() as conexion:
            await conexion.execute(
                text(
                    "INSERT INTO files (id, file_path, file_name, file_format, "
                    "sha256_hash, file_size_bytes) "
                    "VALUES (:i, '/lib/x.cbz', 'x.cbz', 'cbz', :sha, 123)"
                ),
                {"i": file_id, "sha": "a" * 64})

        _alembic("upgrade", "head")

        async with motor.begin() as conexion:
            fila = (await conexion.execute(
                text("SELECT original_sha256, sha256_hash, file_size_bytes "
                     "FROM files WHERE id = :i"),
                {"i": file_id})).one()
        assert fila.original_sha256 is None, (
            "un fichero ya etiquetado no puede inventar su hash original")
        assert fila.sha256_hash == "a" * 64, "el resto de columnas queda intacto"
        assert fila.file_size_bytes == 123
    finally:
        async with motor.begin() as conexion:
            await conexion.execute(text("DELETE FROM files WHERE id = :i"), {"i": file_id})
        _alembic("upgrade", "head", estricto=False)
        await motor.dispose()
