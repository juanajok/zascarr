"""Regresión: la búsqueda de Biblioteca usa la configuración FTS correcta."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import ComicTradition, Issue, Series
from zascarr.services.series import SeriesService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.mark.asyncio
async def test_busqueda_series_usa_fta_espanola_y_encuentra_lobo(url_bd):
    engine = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            lobo = Series(id=uuid4(), title="Lobo", tradition=ComicTradition.AMERICAN)
            criminal = Series(id=uuid4(), title="Criminal", tradition=ComicTradition.AMERICAN)
            catwoman = Series(id=uuid4(), title="Catwoman Annual",
                              tradition=ComicTradition.AMERICAN)
            s.add_all([lobo, criminal, catwoman])
            await s.flush()
            # con_issues=True es lo que usa Biblioteca; un especial NULL también cuenta.
            s.add(Issue(series_id=lobo.id, issue_number=None, volume=1))
            await s.commit()

            servicio = SeriesService(s)
            items, total, _ = await servicio.list_series_paginado(
                page_size=50, search="Lobo", con_issues=True)
            assert [x.title for x in items] == ["Lobo"], (items, total)
            assert total == 1

            items, total, _ = await servicio.list_series_paginado(
                page_size=50, search="Criminal")
            assert [x.title for x in items] == ["Criminal"]
            items, total, _ = await servicio.list_series_paginado(
                page_size=50, search="catwoman")
            assert [x.title for x in items] == ["Catwoman Annual"]
    finally:
        await engine.dispose()
