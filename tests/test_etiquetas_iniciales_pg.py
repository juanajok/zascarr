"""Pool inicial de etiquetas (BL-ETQ): seed idempotente e ideas de la ficha."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import Series, Tag, series_tags
from zascarr.services.etiquetas import NAMESPACE
from zascarr.services.etiquetas_iniciales import (
    DESTACADAS,
    ETIQUETAS_INICIALES,
    ideas_para_empezar,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.mark.asyncio
async def test_la_migracion_siembra_el_pool_y_las_ideas_filtran_lo_ya_puesto():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                total = (await s.execute(
                    select(func.count()).select_from(Tag)
                    .where(Tag.namespace == NAMESPACE))).scalar_one()
                assert total == len(ETIQUETAS_INICIALES)
                serie = Series(id=uuid4(), title="Batman")
                s.add(serie)
                await s.flush()
                ideas = await ideas_para_empezar(s, serie.id)
                assert [t.name for t in ideas] == list(DESTACADAS)
                # Asignar una idea la retira de las siguientes sugerencias.
                tag = next(t for t in ideas if t.name == "noir")
                await s.execute(series_tags.insert().values(
                    series_id=serie.id, tag_id=tag.id, source="manual"))
                await s.commit()
                restantes = await ideas_para_empezar(s, serie.id)
                assert "noir" not in [t.name for t in restantes]
        finally:
            await motor.dispose()
