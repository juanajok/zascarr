# ruff: noqa: E501
"""#664: búsqueda por subcadena normalizada y orden alfabético con sort_title NULL."""
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
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    yield b
    await b.cerrar()


async def _sembrar(banco, titulos):
    async with banco.fabrica() as s:
        for i, (titulo, sort_title, anio) in enumerate(titulos):
            s.add(Series(id=uuid4(), title=titulo, sort_title=sort_title,
                         start_year=anio, tradition=ComicTradition.AMERICAN,
                         created_at=datetime(2020, 1, i + 1, tzinfo=UTC)))
        await s.commit()


async def _buscar(banco, q):
    async with banco.fabrica() as s:
        items, _, _ = await SeriesService(s).list_series_paginado(page_size=20, search=q)
    return [i.title for i in items]


@pytest.mark.asyncio
@pytest.mark.parametrize("q,esperado", [
    ("lobo", "Lobo"), ("catwoman", "Catwoman Annual"), ("criminal", "Criminal"),
    ("catw", "Catwoman Annual"), ("asterix", "Astérix"),
    ("catwoman annual", "Catwoman Annual"), ("lob", "Lobezno"),
    ("crimin", "Criminalística"), ("catwom", "Catwoman"),
])
async def test_busqueda_subcadena_normalizada_pg(banco, q, esperado):
    await _sembrar(banco, [("Lobo", "lobo", 1990), ("Catwoman Annual", None, 2019),
                           ("Criminal", None, 2006), ("Astérix", None, 1961),
                           ("Lobezno", None, 1988), ("Criminalística", None, 2010),
                           ("Catwoman", None, 2018)])
    assert esperado in await _buscar(banco, q)


async def _titulos(banco, orden):
    async with banco.fabrica() as s:
        items, _, _ = await SeriesService(s).list_series_paginado(page_size=20, orden=orden)
    return [i.title for i in items]


@pytest.mark.asyncio
async def test_orden_alfabetico_sin_sort_title_pg(banco):
    await _sembrar(banco, [("Zeta", None, 1990), ("Alfa", None, 2000),
                           ("Beta", None, 1980), ("Año", None, None)])
    assert (await _titulos(banco, "titulo"))[:3] == ["Alfa", "Año", "Beta"]
    assert (await _titulos(banco, "titulo_desc"))[:3] == ["Zeta", "Beta", "Año"]


@pytest.mark.asyncio
async def test_sort_title_presente_gana_al_coalesce_pg(banco):
    await _sembrar(banco, [("Zeta", "aaa", 1990), ("Alfa", None, 2000),
                           ("Beta", None, 1980)])
    assert await _titulos(banco, "titulo") == ["Zeta", "Alfa", "Beta"]


@pytest.mark.asyncio
async def test_desempate_por_anio_y_id_pg(banco):
    ids = [uuid4(), uuid4(), uuid4()]
    async with banco.fabrica() as s:
        for sid in ids:
            s.add(Series(id=sid, title="Misma", sort_title=None, start_year=2000,
                         tradition=ComicTradition.AMERICAN))
        await s.commit()
    async with banco.fabrica() as s:
        items, _, _ = await SeriesService(s).list_series_paginado(page_size=20, orden="titulo")
    assert [i.id for i in items] == sorted(ids)
