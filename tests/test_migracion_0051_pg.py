# ruff: noqa: E501
"""#1088: migración 0051 (last_read_at y visitas) aditiva, reversible y backfill real."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic, bd_efimera_sync, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def _sql(url: str, sql: str, **params):
    motor = create_async_engine(url_asyncpg(url))
    try:
        async with motor.begin() as c:
            r = await c.execute(text(sql), params)
            return r.all() if r.returns_rows else []
    finally:
        await motor.dispose()


def _sql_sync(url, sql, **params):
    return asyncio.run(_sql(url, sql, **params))


def test_migracion_0051_backfill_y_downgrade():
    with bd_efimera_sync(URL) as url:
        alembic(url, "upgrade", "0050")
        sid, iid1, iid2 = ("11111111-1111-1111-1111-111111111111",
                           "22222222-2222-2222-2222-222222222222",
                           "33333333-3333-3333-3333-333333333333")
        _sql_sync(url, "INSERT INTO series (id, title) VALUES (:sid, 'Backfill')", sid=sid)
        _sql_sync(url, "INSERT INTO issues (id, series_id, issue_number, volume) "
                       "VALUES (:iid, :sid, '1', 1), (:issue2, :sid, '2', 1)",
                  iid=iid1, issue2=iid2, sid=sid)
        _sql_sync(url, "INSERT INTO reading_progress (id, issue_id, status, started_at, completed_at) "
                       "VALUES (gen_random_uuid(), :iid, 'completed', "
                       "'2024-01-01T00:00:00Z', '2024-02-01T00:00:00Z')", iid=iid1)
        _sql_sync(url, "INSERT INTO reading_progress (id, issue_id, status) "
                       "VALUES (gen_random_uuid(), :issue2, 'unread')", issue2=iid2)
        alembic(url, "upgrade", "0051")
        fechas = _sql_sync(url, "SELECT last_read_at FROM reading_progress ORDER BY last_read_at NULLS LAST")
        assert fechas[0][0] is not None and fechas[1][0] is None
        assert _sql_sync(url, "SELECT count(*) FROM information_schema.tables "
                              "WHERE table_name = 'series_recent_views'")[0][0] == 1
        alembic(url, "downgrade", "0050")
        assert _sql_sync(url, "SELECT count(*) FROM information_schema.tables "
                              "WHERE table_name = 'series_recent_views'")[0][0] == 0
        assert _sql_sync(url, "SELECT count(*) FROM information_schema.columns "
                              "WHERE table_name = 'reading_progress' AND column_name = 'last_read_at'")[0][0] == 0
