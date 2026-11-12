"""Fase 2 de referencia normalizada: IDs externos, payloads y procedencia (0031)."""
from __future__ import annotations

import json
import os
from uuid import uuid4

import asyncpg
import pytest

URL = os.environ.get("TEST_DATABASE_URL")
DSN = (URL or "").replace("postgresql+asyncpg://", "postgresql://")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture
async def conn():
    c = await asyncpg.connect(DSN)
    try:
        await c.execute("BEGIN")
        yield c
    finally:
        await c.execute("ROLLBACK")
        await c.close()


async def test_issues_tienen_columnas_de_ids_externos(conn):
    columnas = {r["column_name"] for r in await conn.fetch(
        "select column_name from information_schema.columns where table_name='issues'")}
    assert {"gcd_id", "metron_id", "anilist_id", "tebeosfera_slug"} <= columnas
    # Siguen siendo opcionales: no se rellenan por la migración.
    assert await conn.fetchval("select count(*) from issues where gcd_id is not null") == 0


async def test_entity_source_records_guarda_payload_y_procedencia(conn):
    eid = uuid4()
    await conn.execute("""
        INSERT INTO entity_source_records
          (entity_type, entity_id, source, external_id, source_url, payload, license)
        VALUES ('issue',$1,'comic_vine','4000-1','https://example.test/1','{"name":"x"}','CC')
    """, eid)
    fila = await conn.fetchrow(
        "select source, external_id, payload, license "
        "from entity_source_records where entity_id=$1", eid)
    assert fila["source"] == "comic_vine" and fila["external_id"] == "4000-1"
    assert json.loads(fila["payload"]) == {"name": "x"} and fila["license"] == "CC"



async def test_entity_source_records_rechaza_duplicado(conn):
    eid = uuid4()
    await conn.execute("""
        INSERT INTO entity_source_records (entity_type, entity_id, source, external_id)
        VALUES ('issue',$1,'comic_vine','4000-1')
    """, eid)
    with pytest.raises(asyncpg.exceptions.UniqueViolationError):
        await conn.execute("""
            INSERT INTO entity_source_records (entity_type, entity_id, source, external_id)
            VALUES ('issue',$1,'comic_vine','4000-1')
        """, eid)


async def test_entity_source_records_rechaza_tipo_desconocido(conn):
    with pytest.raises(asyncpg.exceptions.CheckViolationError):
        await conn.execute("""
            INSERT INTO entity_source_records (entity_type, entity_id, source, external_id)
            VALUES ('otra',$1,'x','1')
        """, uuid4())


async def test_field_provenance_es_una_fila_por_campo(conn):
    eid = uuid4()
    await conn.execute("""
        INSERT INTO field_provenance (entity_type, entity_id, field, source, value)
        VALUES ('series',$1,'start_year','gcd','{"year":1987}')
    """, eid)
    valor = await conn.fetchval(
        "select value from field_provenance where entity_id=$1 and field='start_year'", eid)
    assert json.loads(valor) == {"year": 1987}
    await conn.execute("""
        UPDATE field_provenance SET source='manual', locked=true
        WHERE entity_id=$1 AND field='start_year'
    """, eid)
    fila = await conn.fetchrow(
        "select source, locked from field_provenance where entity_id=$1", eid)
    assert (fila["source"], fila["locked"]) == ("manual", True)
