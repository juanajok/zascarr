# ruff: noqa: F401, F811
"""#1077: filtro y orden por MAX(rating) sobre PostgreSQL real."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import entorno  # noqa: F401
from zascarr.models import File, FileFormat, Issue, ReadingProgress, ReadingStatus, Series
from zascarr.services.series import SeriesService

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"),
                                reason="requiere TEST_DATABASE_URL")


async def _serie(s, titulo):
    sid = uuid4()
    s.add(Series(id=sid, title=titulo))
    await s.flush()
    iid = uuid4()
    s.add(Issue(id=iid, series_id=sid, issue_number="1", volume=1))
    await s.flush()
    s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}.cbz",
               file_name="x.cbz", file_format=FileFormat.CBZ, metadata_={}, is_missing=False))
    await s.flush()
    return sid, iid


async def _rating(s, iid, valor):
    s.add(ReadingProgress(id=uuid4(), issue_id=iid, status=ReadingStatus.COMPLETED, rating=valor))
    await s.flush()


@pytest.mark.asyncio
async def test_max_filtros_y_nulls_al_final(entorno):
    async with entorno.banco.fabrica() as s:
        a, ai = await _serie(s, "Alta")
        b, bi = await _serie(s, "Baja")
        c, _ci = await _serie(s, "Sin valorar")
        await _rating(s, ai, 3)
        await _rating(s, bi, 5)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        con, total_con, _ = await SeriesService(s).list_series_paginado(puntuacion="con")
        sin, total_sin, _ = await SeriesService(s).list_series_paginado(puntuacion="sin")
        altas, total_45, _ = await SeriesService(s).list_series_paginado(puntuacion="4-5")
        orden, total_orden, _ = await SeriesService(s).list_series_paginado(orden="valoracion")
    assert total_con == 2 and {x.title for x in con} == {"Alta", "Baja"}
    assert total_sin == 1 and sin[0].title == "Sin valorar"
    assert total_45 == 1 and altas[0].title == "Baja"
    assert total_orden == 3
    assert [x.title for x in orden] == ["Baja", "Alta", "Sin valorar"]


@pytest.mark.asyncio
async def test_empates_paginacion_y_una_agregada(entorno):
    async with entorno.banco.fabrica() as s:
        for titulo, valor in (("Zeta", 5), ("Alfa", 5), ("Beta", 3)):
            sid, iid = await _serie(s, titulo)
            await _rating(s, iid, valor)
            if titulo == "Zeta":
                iid2 = uuid4()
                s.add(Issue(id=iid2, series_id=sid, issue_number="2", volume=1))
                await s.flush()
                await _rating(s, iid2, 1)  # el máximo manda; no duplica
        await s.commit()
    async with entorno.banco.fabrica() as s:
        items, total, pagina = await SeriesService(s).list_series_paginado(
            orden="valoracion", page=1, page_size=2)
        segunda, total2, _ = await SeriesService(s).list_series_paginado(
            orden="valoracion", page=2, page_size=2)
        antes = len(entorno.banco.sentencias)
        await SeriesService(s).list_series_paginado(orden="valoracion")
        consultas = len(entorno.banco.sentencias) - antes
    assert total == total2 == 3 and pagina == 1
    assert [x.title for x in items] == ["Alfa", "Zeta"]
    assert [x.title for x in segunda] == ["Beta"]
    assert consultas <= 2  # count + página; el MAX va en subconsulta
