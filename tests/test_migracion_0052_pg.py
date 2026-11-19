"""#1115: migración 0052 añade el valor hispanoamericano."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic, bd_efimera_sync, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")


async def _valores(url):
    motor = create_async_engine(url_asyncpg(url))
    try:
        async with motor.begin() as c:
            return [r[0] for r in (await c.execute(text(
                "SELECT enumlabel FROM pg_enum JOIN pg_type ON pg_type.oid = enumtypid "
                "WHERE typname = 'comic_tradition'"))).all()]
    finally:
        await motor.dispose()


def test_valor_hispanoamericano_existe():
    with bd_efimera_sync(URL) as url:
        alembic(url, "upgrade", "0052")
        valores = asyncio.run(_valores(url))
    assert "hispanoamericano" in valores


def test_cadena_desde_cero_no_siembra_el_valor_nuevo():
    with bd_efimera_sync(URL) as url:
        alembic(url, "upgrade", "head")
        valores = asyncio.run(_valores(url))
        async def _semillas():
            motor = create_async_engine(url_asyncpg(url))
            try:
                async with motor.begin() as c:
                    r = await c.execute(text(
                        "SELECT tradition FROM library_root_traditions"))
                    return [x[0] for x in r.all()]
            finally:
                await motor.dispose()
        semillas = asyncio.run(_semillas())
    assert "hispanoamericano" in valores
    assert "hispanoamericano" not in semillas
