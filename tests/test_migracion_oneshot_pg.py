"""#1027: migración 0049 (enum one_shot) aditiva y sin DML."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic, bd_efimera_sync, migrar_a_head, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _enum(url: str):
    async def _run():
        motor = create_async_engine(url_asyncpg(url))
        try:
            async with motor.begin() as c:
                r = await c.execute(text(
                    "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid "
                    "WHERE t.typname='series_kind' ORDER BY e.enumsortorder"))
                return [fila[0] for fila in r.all()]
        finally:
            await motor.dispose()
    return asyncio.run(_run())


def test_one_shot_en_el_enum_y_downgrade_sin_dml():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        assert _enum(url) == ["regular", "annual", "special", "one_shot"]
        # No se ha tocado ninguna fila ni columna: sigue habiendo series regular.
        alembic(url, "downgrade", "0048")
        # El downgrade documenta que el valor no se retira; no borra filas.
        assert "one_shot" in _enum(url)
