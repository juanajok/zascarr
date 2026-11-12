# ruff: noqa: E501
"""#264 A: migración 0030 aditiva y reversible (Postgres real)."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic, bd_efimera_sync, migrar_a_head, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def _consultar(url: str, sql: str):
    motor = create_async_engine(url_asyncpg(url))
    try:
        async with motor.connect() as c:
            return (await c.execute(text(sql))).all()
    finally:
        await motor.dispose()


def _consultar_sync(url: str, sql: str):
    return asyncio.run(_consultar(url, sql))


def test_upsert_tablas_enums_y_bajada():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        tablas = _consultar_sync(
            url, "SELECT tablename FROM pg_tables WHERE tablename LIKE 'apartado_%' ORDER BY 1")
        assert [t[0] for t in tablas] == ["apartado_grupos", "apartado_operaciones"]
        enums = _consultar_sync(
            url, "SELECT typname FROM pg_type WHERE typname LIKE 'apartado_%' AND typtype = 'e' ORDER BY 1")
        assert [e[0] for e in enums] == ["apartado_estado", "apartado_grupo_estado"]
        uniques = _consultar_sync(
            url, "SELECT indexname FROM pg_indexes WHERE tablename = 'apartado_grupos' "
                 "AND indexname = 'uq_apartado_grupo_operacion_clave'")
        assert uniques
        alembic(url, "downgrade", "0029")
        assert not _consultar_sync(
            url, "SELECT tablename FROM pg_tables WHERE tablename LIKE 'apartado_%'")
        assert not _consultar_sync(
            url, "SELECT typname FROM pg_type WHERE typname LIKE 'apartado_%' AND typtype = 'e'")
