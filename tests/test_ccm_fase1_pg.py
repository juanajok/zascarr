"""CCM Fase 1: UPSERT real en `entity_source_records` (Postgres real)."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import url_asyncpg
from zascarr.core.consolidacion.tipos import FichaRecolectada
from zascarr.services.consolidacion.recolector import Recolector

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _ficha() -> FichaRecolectada:
    return FichaRecolectada(
        fuente="comic_vine", entidad="series", external_id="4050",
        url="https://example.test/volume/4050",
        licencia="Comic Vine API Terms (uso no comercial)",
        raw_acotado={"name": "Batman"}, normalizado={"edition_scope": {"title": "Batman"}},
        normalizer_version=1, payload_hash="a" * 64, observado_en=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_guardar_es_upsert_por_entidad_fuente_y_external_id():
    assert URL is not None
    engine = create_async_engine(url_asyncpg(URL))
    sesion_factory = async_sessionmaker(engine, expire_on_commit=False)
    series_id = uuid4()
    ficha = _ficha()
    try:
        async with sesion_factory() as db, db.begin():
            recolector = Recolector(db, {})
            await recolector._guardar(series_id, ficha)
            await recolector._guardar(series_id, ficha)
            filas = (await db.execute(text(
                "select count(*), min(source), min(external_id) "
                "from entity_source_records where entity_id = :e"
            ), {"e": series_id})).one()
            assert filas[0] == 1
            assert (filas[1], filas[2]) == ("comic_vine", "4050")
    finally:
        await engine.dispose()
