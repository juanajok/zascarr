"""SCR3 O2 — reconciliación de guías contra Postgres real (skip sin TEST_DATABASE_URL).

Prueba lo que el doble de `FakeSession` no puede demostrar: que la segunda pasada es
idempotente de verdad (mismas filas, no duplicados), que escribe SOLO el arco y sus enlaces y
que la biblioteca (`series`, `issues`, `files`) queda intacta.
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    Series,
    StoryArc,
    StoryArcIssue,
)
from zascarr.services.reading_orders.comun import GuiaLeida, RawReadingEntry
from zascarr.services.reconciliacion_lecturas import reconciliar_guia

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = [pytest.mark.asyncio,
              pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")]

GUIA_URL = "https://comicbookreadingorders.com/dc/events/batman-reading-order/"


def _guia() -> GuiaLeida:
    return GuiaLeida(
        sitio="reading_orders",
        url=GUIA_URL,
        titulo="Batman: guía de prueba",
        entradas=(
            RawReadingEntry(orden=1, referencia="Batman #1", seccion=None, item_url=None),
            RawReadingEntry(orden=2, referencia="Batman #2", seccion=None, item_url=None),
            RawReadingEntry(orden=3, referencia="Batman #3 (no existe)", seccion=None,
                            item_url=None),
        ),
    )


async def _contar(db, modelo) -> int:
    return (await db.execute(select(func.count()).select_from(modelo))).scalar_one()


async def test_reconciliar_guia_pg_crea_arco_en_orden_e_es_idempotente():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fabrica = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fabrica() as db:
                serie = Series(id=uuid4(), title="Batman",
                               tradition=ComicTradition.AMERICAN)
                db.add(serie)
                await db.flush()
                issues = [Issue(id=uuid4(), series_id=serie.id, issue_number=numero)
                          for numero in ("1", "2")]
                db.add_all(issues)
                await db.flush()
                archivo = File(id=uuid4(), file_path="/lib/batman-1.cbz",
                               file_name="batman-1.cbz", file_format=FileFormat.CBZ,
                               issue_id=issues[0].id)
                db.add(archivo)
                await db.commit()
                ids_serie, ids_issues, ids_archivo = serie.id, {i.id for i in issues}, archivo.id

                primero = await reconciliar_guia(db, _guia())
                await db.commit()

                assert primero.creado and primero.enlazados == 2 and primero.omitidos == 1
                arco = (await db.execute(
                    select(StoryArc).where(StoryArc.title == primero.titulo)
                )).scalar_one()
                assert arco.metadata_ == {"origen": "reading_orders", "url": GUIA_URL}
                enlaces = (await db.execute(
                    select(StoryArcIssue).where(StoryArcIssue.story_arc_id == arco.id)
                    .order_by(StoryArcIssue.reading_order))).scalars().all()
                assert [(e.issue_id, e.reading_order) for e in enlaces] == [
                    (issues[0].id, 1), (issues[1].id, 2)]

                # Segunda pasada: mismo arco, mismos enlaces, sin duplicar.
                segundo = await reconciliar_guia(db, _guia())
                await db.commit()
                assert not segundo.creado and segundo.enlazados == 2
                assert await _contar(db, StoryArc) == 1
                assert await _contar(db, StoryArcIssue) == 2
                enlaces_2 = (await db.execute(
                    select(StoryArcIssue).where(StoryArcIssue.story_arc_id == arco.id)
                    .order_by(StoryArcIssue.reading_order))).scalars().all()
                assert [(e.issue_id, e.reading_order) for e in enlaces_2] == [
                    (issues[0].id, 1), (issues[1].id, 2)]

                # La biblioteca y los ficheros no se tocan (solo lectura + arco/enlaces).
                assert await _contar(db, Series) == 1
                assert await _contar(db, Issue) == 2
                assert await _contar(db, File) == 1
                serie_db = (await db.execute(
                    select(Series).where(Series.id == ids_serie))).scalar_one()
                assert serie_db.title == "Batman"
                numeros = set((await db.execute(
                    select(Issue.id).where(Issue.series_id == ids_serie))).scalars().all())
                assert numeros == ids_issues
                archivo_db = (await db.execute(
                    select(File).where(File.id == ids_archivo))).scalar_one()
                assert archivo_db.file_path == "/lib/batman-1.cbz"
                assert archivo_db.issue_id == issues[0].id
        finally:
            await motor.dispose()
