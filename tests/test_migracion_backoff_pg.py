"""T-62: migración 0046 (backoff de envíos) aditiva y reversible (Postgres real).

Comprueba en la BD de verdad lo que el modelo asume: las dos columnas nuevas
con sus tipos y default, y que el `downgrade` las retira sin tocar el resto.
Se salta sin `TEST_DATABASE_URL`, mismo patrón que `test_migracion_apartado_pg.py`.
"""
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
        async with motor.begin() as c:
            resultado = await c.execute(text(sql))
            return resultado.all() if resultado.returns_rows else []
    finally:
        await motor.dispose()


def _consultar_sync(url: str, sql: str):
    return asyncio.run(_consultar(url, sql))


def test_columnas_aditivas_y_reversibles():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        columnas = _consultar_sync(
            url,
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_name = 'wishlist' "
            "AND column_name IN ('retry_count', 'next_retry_at') "
            "ORDER BY 1",
        )
        assert [(c[0], c[1], c[2]) for c in columnas] == [
            ("next_retry_at", "timestamp with time zone", "YES"),
            ("retry_count", "integer", "NO"),
        ]
        # Default 0: las filas que ya existían quedan elegibles sin reescribirlas.
        assert "0" in (columnas[1][3] or "")

        alembic(url, "downgrade", "0045")
        restantes = _consultar_sync(
            url,
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'wishlist' "
            "AND column_name IN ('retry_count', 'next_retry_at')",
        )
        assert restantes == []
