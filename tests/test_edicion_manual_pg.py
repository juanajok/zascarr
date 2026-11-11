"""BL-INF5 (#591): edición manual por campo, bloqueos, validación y colisión (PG)."""
from __future__ import annotations

import os
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import Issue, IssueFormat, MetadataSource, Series
from zascarr.services.edicion_manual import (
    desbloquear_numero,
    desbloquear_serie,
    guardar_numero,
    guardar_serie,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.mark.asyncio
async def test_editar_serie_marca_manual_y_bloquea_sin_cambiar_metadata_source():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                serie = Series(id=uuid4(), title="Original", start_year=1980,
                               metadata_source=MetadataSource.COMIC_VINE.value,
                               metadata_={"otra": "cosa"}, locked_fields=[])
                s.add(serie)
                await s.commit()
                r = await guardar_serie(
                    s, serie.id, title="Corregida", start_year="1981", end_year="",
                    publisher="Norma", description="Sinopsis nueva", total_issues="12")
                assert r.ok and r.cambios["title"] == "Corregida"
                await s.commit()
                await s.refresh(serie)
                assert serie.title == "Corregida" and serie.start_year == 1981
                assert serie.total_issues == 12
                assert serie.metadata_source == MetadataSource.COMIC_VINE.value
                assert serie.metadata_["otra"] == "cosa"
                assert set(serie.locked_fields) == {"title", "start_year", "publisher",
                                                   "description", "total_issues"}
                for campo in serie.locked_fields:
                    assert "fecha" in serie.metadata_["manual"][campo]
                # Desbloquear no borra el valor.
                assert await desbloquear_serie(s, serie.id, "title")
                await s.commit()
                await s.refresh(serie)
                assert serie.title == "Corregida"
                assert "title" not in serie.locked_fields
                assert "title" not in serie.metadata_["manual"]
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_validaciones_no_escriben_nada():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                serie = Series(id=uuid4(), title="Original", locked_fields=[])
                s.add(serie)
                await s.commit()
                r = await guardar_serie(
                    s, serie.id, title="", start_year="no", end_year="",
                    publisher="", description="", total_issues="-1")
                assert not r.ok
                assert {"title", "start_year", "total_issues"} <= set(r.errores)
                await s.refresh(serie)
                assert serie.title == "Original" and serie.locked_fields == []
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_numero_colision_y_sort_order():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                serie = Series(id=uuid4(), title="Serie")
                s.add(serie)
                await s.flush()
                uno = Issue(id=uuid4(), series_id=serie.id, issue_number="1",
                            volume=1, format=IssueFormat.SINGLE_ISSUE)
                dos = Issue(id=uuid4(), series_id=serie.id, issue_number="2",
                            volume=1, format=IssueFormat.SINGLE_ISSUE)
                s.add_all([uno, dos])
                await s.commit()
                r = await guardar_numero(
                    s, serie.id, dos.id, issue_number="1", title="", release_date="",
                    format="single_issue", synopsis="")
                assert not r.ok and "Ya existe el nº 1" in r.errores["issue_number"]
                r = await guardar_numero(
                    s, serie.id, dos.id, issue_number="2.5", title="Especial",
                    release_date="1985-04-01", format="single_issue",
                    synopsis="Sinopsis editada")
                assert r.ok
                await s.commit()
                await s.refresh(dos)
                assert dos.issue_number == "2.5" and dos.sort_order == 2.5
                assert dos.release_date == date(1985, 4, 1)
                assert set(dos.locked_fields) == {"issue_number", "title",
                                                 "release_date", "synopsis"}
                assert await desbloquear_numero(s, serie.id, dos.id, "issue_number")
                await s.commit()
                await s.refresh(dos)
                assert dos.issue_number == "2.5" and "issue_number" not in dos.locked_fields
        finally:
            await motor.dispose()
