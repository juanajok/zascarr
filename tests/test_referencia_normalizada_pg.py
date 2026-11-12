"""Referencia normalizada (migración 0030) — Postgres real.

Comprueba las funciones generadas, la vista de issue y los casos límite del
número canónico. No toca archivos ni la identidad editorial.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import asyncpg
import pytest

URL = os.environ.get("TEST_DATABASE_URL")
DSN = (URL or "").replace("postgresql+asyncpg://", "postgresql://")
pytestmark = pytest.mark.skipif(
    not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture
async def conn():
    c = await asyncpg.connect(DSN)
    try:
        await c.execute("BEGIN")
        yield c
    finally:
        await c.execute("ROLLBACK")
        await c.close()


async def _serie(c, title: str, *, year: int | None = None, volume: int | None = None) -> UUID:
    sid = uuid4()
    await c.execute(
        """INSERT INTO series (id, title, start_year, volume, tradition, kind)
           VALUES ($1, $2, $3, $4, 'american', 'regular')""",
        sid, title, year, volume)
    return sid


async def _issue(c, serie: UUID, number: str | None) -> UUID:
    iid = uuid4()
    await c.execute(
        """INSERT INTO issues (id, series_id, issue_number, volume, format)
           VALUES ($1, $2, $3, 1, 'single_issue')""",
        iid, serie, number)
    return iid


@pytest.mark.parametrize("entrada,esperado", [
    ("001", "1"),
    ("000", "0"),
    ("012a", "12a"),
    ("023.1", "23.1"),
    ("023.1a", "23.1a"),
    ("E1", "e1"),
    ("2A3", "2a3"),
    (" 007 ", "7"),
    ("", None),
    (None, None),
])
async def test_number_key_canoniza_sin_colapsar_formas(conn, entrada, esperado):
    assert await conn.fetchval("SELECT f_number_key($1)", entrada) == esperado


async def test_series_reference_incluye_anio_y_volumen_sin_duplicar(conn):
    sid = await _serie(conn, "Batman", year=1940, volume=1)
    assert (await conn.fetchrow(
        "SELECT volume, reference_name FROM series WHERE id=$1", sid)) == (
        (1, "Batman (1940) Vol. 1"))

    sid2 = await _serie(conn, "Catwoman Vol. 4", year=2011, volume=4)
    ref2 = await conn.fetchval("SELECT reference_name FROM series WHERE id=$1", sid2)
    assert ref2 == "Catwoman Vol. 4 (2011)"       # no duplica «Vol. 4»


async def test_issue_reference_usa_number_key_y_no_inventa_numero(conn):
    sid = await _serie(conn, "Batman", year=1940, volume=1)
    iid = await _issue(conn, sid, "001")
    fila = await conn.fetchrow(
        "SELECT number_key, reference_name FROM v_issue_reference WHERE issue_id=$1", iid)
    assert dict(fila) == {
        "number_key": "1",
        "reference_name": "Batman (1940) Vol. 1 #1",
    }

    iid2 = await _issue(conn, sid, None)
    await conn.execute("UPDATE issues SET title='Especial' WHERE id=$1", iid2)
    ref = await conn.fetchval(
        "SELECT reference_name FROM v_issue_reference WHERE issue_id=$1", iid2)
    assert ref == "Batman (1940) Vol. 1 — Especial"


async def test_number_key_no_es_unico_ni_sustituye_issue_number(conn):
    sid = await _serie(conn, "Serie")
    a = await _issue(conn, sid, "01")
    b = await _issue(conn, sid, "1a")
    assert (await conn.fetchval("SELECT number_key FROM issues WHERE id=$1", a)) == "1"
    assert (await conn.fetchval("SELECT number_key FROM issues WHERE id=$1", b)) == "1a"
    # Las dos filas coexisten: la clave no es única.
    assert await conn.fetchval(
        "SELECT count(*) FROM issues WHERE series_id=$1", sid) == 2
