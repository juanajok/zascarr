"""BL-C4 (#151): arcos en orden de lectura, incluso entre series (PG real)."""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import File, FileFormat, Issue, Series, StoryArc, StoryArcIssue
from zascarr.services.arcos import detalle_arco, listar_arcos

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.mark.asyncio
async def test_arco_cruza_series_y_respeta_reading_order():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                a = Series(id=uuid4(), title="Batman")
                b = Series(id=uuid4(), title="Nightwing")
                s.add_all([a, b])
                await s.flush()
                i1 = Issue(id=uuid4(), series_id=a.id, issue_number="1", volume=1,
                           release_date=date(2011, 1, 1))
                i2 = Issue(id=uuid4(), series_id=b.id, issue_number="2", volume=1)
                s.add_all([i1, i2])
                await s.flush()
                s.add(File(id=uuid4(), file_path="/lib/b1.cbz", file_name="b1.cbz",
                           file_format=FileFormat.CBZ, issue_id=i1.id,
                           is_missing=False))
                arco = StoryArc(id=uuid4(), title="Court of Owls", is_crossover=True,
                                description="Orden cruzado")
                s.add(arco)
                await s.flush()
                s.add_all([
                    StoryArcIssue(story_arc_id=arco.id, issue_id=i2.id, reading_order=2),
                    StoryArcIssue(story_arc_id=arco.id, issue_id=i1.id, reading_order=1),
                ])
                await s.commit()
                pagina = await listar_arcos(s)
                assert pagina.total == 1 and pagina.filas[0].numeros == 2
                assert pagina.filas[0].series == 2 and pagina.filas[0].is_crossover
                detalle = await detalle_arco(s, arco.id)
                assert [f.series for f in detalle.filas] == ["Batman", "Nightwing"]
                assert [f.orden for f in detalle.filas] == [1, 2]
                assert detalle.filas[0].disponible is True
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_crud_manual_de_una_saga():
    from zascarr.models import StoryArcIssue
    from zascarr.services.arcos import (
        agregar_numero,
        crear_arco,
        editar_arco,
        eliminar_arco,
        mover_numero,
        quitar_numero,
    )
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                a = Series(id=uuid4(), title="Batman")
                b = Series(id=uuid4(), title="Nightwing")
                s.add_all([a, b]); await s.flush()
                i1 = Issue(id=uuid4(), series_id=a.id, issue_number="1", volume=1)
                i2 = Issue(id=uuid4(), series_id=b.id, issue_number="2", volume=1)
                s.add_all([i1, i2]); await s.commit()
                r = await crear_arco(s, title="Saga nueva", description="", is_crossover=True)
                assert r.ok and r.arco.title == "Saga nueva"
                arc_id = r.arco.id
                r = await editar_arco(s, arc_id, title="Saga editada", description="D",
                                      is_crossover=False)
                assert r.ok and r.arco.title == "Saga editada"
                assert (await agregar_numero(s, arc_id, serie="Batman", numero="1")).ok
                assert (await agregar_numero(s, arc_id, serie="Nightwing", numero="2")).ok
                dup = await agregar_numero(s, arc_id, serie="Batman", numero="1")
                assert not dup.ok and "ya está" in dup.errores["numero"]
                await mover_numero(s, arc_id, i2.id, subir=True)
                filas = (await s.execute(select(StoryArcIssue).where(
                    StoryArcIssue.story_arc_id == arc_id)
                    .order_by(StoryArcIssue.reading_order))).scalars().all()
                assert [f.issue_id for f in filas] == [i2.id, i1.id]
                assert await quitar_numero(s, arc_id, i2.id)
                assert await eliminar_arco(s, arc_id)
                await s.commit()
                assert (await s.get(Issue, i1.id)) is not None
                assert (await s.get(Issue, i2.id)) is not None
                assert (await s.get(StoryArcIssue, (arc_id, i1.id))) is None
        finally:
            await motor.dispose()
