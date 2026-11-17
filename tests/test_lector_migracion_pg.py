"""Migración 0050 (BL-LEC1): `reading_progress.file_id`, FK e índice — Postgres real."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera_sync, migrar_a_head, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def _consultar(url: str, sql: str):
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    try:
        async with motor.connect() as c:
            return (await c.execute(text(sql))).all()
    finally:
        await motor.dispose()


def test_0050_crea_columna_fk_indice_y_es_reversible():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        columnas = asyncio.run(_consultar(url, """
            SELECT column_name, is_nullable FROM information_schema.columns
            WHERE table_name='reading_progress' AND column_name='file_id'
        """))
        assert columnas == [("file_id", "YES")]
        fk = asyncio.run(_consultar(url, """
            SELECT COUNT(*) FROM information_schema.table_constraints
            WHERE table_name='reading_progress' AND constraint_type='FOREIGN KEY'
              AND constraint_name='reading_progress_file_id_fkey'
        """))
        assert fk == [(1,)]
        indice = asyncio.run(_consultar(url, """
            SELECT COUNT(*) FROM pg_indexes
            WHERE tablename='reading_progress' AND indexname='ix_reading_progress_file_id'
        """))
        assert indice == [(1,)]
        alembic(url, "downgrade", "0049")
        columnas = asyncio.run(_consultar(url, """
            SELECT column_name FROM information_schema.columns
            WHERE table_name='reading_progress' AND column_name='file_id'
        """))
        assert columnas == []
