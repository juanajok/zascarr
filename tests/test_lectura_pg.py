# ruff: noqa: E501
"""#150 BL-C3 sobre PostgreSQL real: upsert, unique e idempotencia."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, Issue, ReadingProgress, Series
from zascarr.services.lectura import marcar

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
    yield SimpleNamespace(banco=banco)
    await banco.cerrar()


async def _issue(entorno):
    sid, iid = uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN))
        await s.flush()
        s.add(Issue(id=iid, series_id=sid, issue_number="3"))
        await s.commit()
    return iid


@pytest.mark.asyncio
async def test_upsert_unique_y_repetir_no_duplica_pg(entorno):
    iid = await _issue(entorno)
    async with entorno.banco.fabrica() as s:
        r = await marcar(s, iid, "completed", rating=4, nota="Muy bueno")
        assert r.completed_at is not None
        r2 = await marcar(s, iid, "completed", rating=4, nota="Muy bueno")
        assert r2.completed_at == r.completed_at
    async with entorno.banco.fabrica() as s:
        filas = (await s.execute(select(ReadingProgress).where(
            ReadingProgress.issue_id == iid))).scalars().all()
        assert len(filas) == 1 and filas[0].status.value == "completed"
        assert filas[0].completed_at is not None and filas[0].rating == 4


@pytest.mark.asyncio
async def test_desmarcar_conserva_opinion_y_no_toca_pagina_pg(entorno):
    iid = await _issue(entorno)
    async with entorno.banco.fabrica() as s:
        await marcar(s, iid, "completed", rating=5, nota="Obra maestra")
        r = await marcar(s, iid, "unread")
    async with entorno.banco.fabrica() as s:
        p = (await s.execute(select(ReadingProgress).where(
            ReadingProgress.issue_id == iid))).scalar_one()
        assert p.status.value == "unread" and p.completed_at is None
        assert p.rating == 5 and p.notes == "Obra maestra" and p.current_page == 0
        assert r.estado.value == "unread"
