# ruff: noqa: E501
"""BL-INF11 (#628): criterios de orden de la biblioteca con Postgres real."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, Series
from zascarr.services.series import SeriesService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd):
    banco = Banco(url_bd)
    await banco.limpiar()
    yield banco
    await banco.cerrar()


async def _sembrar(entorno):
    async with entorno.fabrica() as s:
        s.add_all([
            Series(id=uuid4(), title="Alfa", sort_title="alfa", start_year=2000,
                   tradition=ComicTradition.AMERICAN, created_at=datetime(2020, 1, 1, tzinfo=UTC)),
            Series(id=uuid4(), title="Beta", sort_title="beta", start_year=None,
                   tradition=ComicTradition.AMERICAN, created_at=datetime(2021, 1, 1, tzinfo=UTC)),
            Series(id=uuid4(), title="Gamma", sort_title="gamma", start_year=1990,
                   tradition=ComicTradition.AMERICAN, created_at=datetime(2022, 1, 1, tzinfo=UTC)),
        ])
        await s.commit()


async def _titulos(entorno, orden):
    async with entorno.fabrica() as s:
        items, total, _ = await SeriesService(s).list_series_paginado(
            page_size=10, orden=orden)
    assert total == 3
    return [i.title for i in items]


@pytest.mark.asyncio
@pytest.mark.parametrize("orden,esperado", [
    ("titulo", ["Alfa", "Beta", "Gamma"]),
    ("titulo_desc", ["Gamma", "Beta", "Alfa"]),
    ("anio_desc", ["Alfa", "Gamma", "Beta"]),
    ("anio_asc", ["Gamma", "Alfa", "Beta"]),
    ("reciente", ["Gamma", "Beta", "Alfa"]),
    ("desconocido", ["Alfa", "Beta", "Gamma"]),
    ("", ["Alfa", "Beta", "Gamma"]),
])
async def test_cada_criterio_y_null_al_final(entorno, orden, esperado):
    await _sembrar(entorno)
    assert await _titulos(entorno, orden) == esperado


@pytest.mark.asyncio
async def test_desempate_determinista_pg(entorno):
    ids = [uuid4(), uuid4(), uuid4()]
    async with entorno.fabrica() as s:
        for i, sid in enumerate(ids):
            s.add(Series(id=sid, title=f"Misma {i}", sort_title="misma", start_year=2000,
                         tradition=ComicTradition.AMERICAN))
        await s.commit()
    async with entorno.fabrica() as s:
        items, _, _ = await SeriesService(s).list_series_paginado(page_size=10, orden="titulo")
        assert [i.id for i in items] == sorted(ids)
    async with entorno.fabrica() as s:
        items, _, _ = await SeriesService(s).list_series_paginado(page_size=10, orden="titulo_desc")
        assert [i.id for i in items] == sorted(ids, reverse=True)
