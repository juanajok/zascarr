# ruff: noqa: E501
"""#423 (C6-O1): la ficha y el enriquecedor deciden igual con Comic Vine (PG real)."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, MetadataSource, Series
from zascarr.services.enricher import (
    _COMIC_VINE_TRADITIONS,
    _condiciones_pendientes,
    puede_enlazarse_con_comic_vine,
)

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


@pytest.mark.asyncio
async def test_paridad_entre_python_y_sql_para_comic_vine(banco):
    ahora = datetime.now(UTC)
    async with banco.fabrica() as s:
        s.add_all([
            Series(id=uuid4(), title="Elegible", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.COMIC_VINE.value),
            Series(id=uuid4(), title="Reciente", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.COMIC_VINE.value,
                   enrichment_attempted_at=ahora - timedelta(days=1)),
            Series(id=uuid4(), title="Antigua", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.COMIC_VINE.value,
                   enrichment_attempted_at=ahora - timedelta(days=31)),
            Series(id=uuid4(), title="Fandom DC", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.FANDOM_DC.value, fandom_dc_slug="x"),
            Series(id=uuid4(), title="Fandom Marvel", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.FANDOM_MARVEL.value, fandom_marvel_slug="y"),
            Series(id=uuid4(), title="Manga", tradition=ComicTradition.MANGA,
                   metadata_source=MetadataSource.ANILIST.value),
            Series(id=uuid4(), title="Manual", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.MANUAL.value),
            Series(id=uuid4(), title="AniList", tradition=ComicTradition.AMERICAN,
                   metadata_source=MetadataSource.COMIC_VINE.value, anilist_id=99),
        ])
        await s.commit()

    async with banco.fabrica() as s:
        filas = (await s.execute(select(Series).order_by(Series.title))).scalars().all()
        sql_ids = set((await s.execute(
            select(Series.id).where(
                *_condiciones_pendientes(ahora),
                Series.tradition.in_(_COMIC_VINE_TRADITIONS),
            )
        )).scalars().all())
        elegibles = {
            fila.id for fila in filas
            if puede_enlazarse_con_comic_vine(
                fila, True, "clave", ahora=ahora)
        }
        assert elegibles == sql_ids
        assert {f.title for f in filas if f.id in elegibles} == {"Elegible", "Antigua"}
        assert all(not puede_enlazarse_con_comic_vine(f, True, "", ahora=ahora) for f in filas)
