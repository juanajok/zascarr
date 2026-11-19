"""CCM-2: backfill conservador y aplicación transaccional (Postgres real)."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import url_asyncpg
from zascarr.models import ComicTradition, EntitySourceRecord, FieldProvenance, Series
from zascarr.services.consolidacion.aplicador import Aplicador, PlanCaducadoError
from zascarr.services.consolidacion.backfill import Backfill
from zascarr.services.consolidacion.consulta import cargar_contexto

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _serie(**kw) -> Series:
    base = dict(title="Patrulla-X", tradition=ComicTradition.AMERICAN,
                metadata_={}, locked_fields=[])
    base.update(kw)
    return Series(**base)


@pytest.mark.asyncio
async def test_backfill_marca_legado_y_respeta_lock():
    assert URL is not None
    engine = create_async_engine(url_asyncpg(URL))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as db, db.begin():
            serie = _serie(
                start_year=1985, end_year=2011, language="en", total_issues=12,
                metadata_={
                    "manual": {"start_year": {"fecha": "2026-11-01T00:00:00Z"}},
                    "relleno": {"gcd": {"campos": ["end_year"], "url_ficha": "https://gcd.test/1"}},
                },
                locked_fields=["total_issues"],
                metadata_source="comic_vine",
            )
            db.add(serie)
            await db.flush()
            await Backfill(db).ejecutar(limite=1000)
            filas = {
                f.field: f for f in (await db.execute(
                    select(FieldProvenance).where(
                        FieldProvenance.entity_type == "series",
                        FieldProvenance.entity_id == serie.id)
                )).scalars().all()
            }
        assert filas["start_year"].source == "manual"
        assert filas["start_year"].value["confianza"] == "manual"
        assert filas["end_year"].source == "gcd"
        assert filas["end_year"].value["confianza"] == "secundaria"
        assert filas["language"].source == "comic_vine"
        assert filas["language"].value["legado"] is True
        assert filas["total_issues"].locked is True
        assert filas["total_issues"].source == "desconocido"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_aplicador_actualiza_solo_edicion_propia_y_deja_procedencia():
    assert URL is not None
    engine = create_async_engine(url_asyncpg(URL))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as db, db.begin():
            serie = _serie(start_year=None, total_issues=None,
                           metadata_={"vinculos_rol": {"comic_vine": "edicion_propia"}})
            db.add(serie)
            await db.flush()
            db.add(EntitySourceRecord(
                entity_type="series", entity_id=serie.id,
                source="comic_vine", external_id="4050",
                payload={"normalizado": {"edition_scope": {
                    "start_year": 1963, "total_issues": 544}}},
                payload_hash="h1", license="CV",
            ))
            await db.flush()
            contexto = await cargar_contexto(db, serie.id)
            plan = contexto.plan()
            resultado = await Aplicador(db).aplicar(plan)
            await db.flush()
            actual = await db.get(Series, serie.id)
            filas = (await db.execute(
                select(FieldProvenance.field, FieldProvenance.source).where(
                    FieldProvenance.entity_id == serie.id)
            )).all()
        assert set(resultado.campos) == {"start_year", "total_issues"}
        assert actual.start_year == 1963 and actual.total_issues == 544
        assert dict(filas) == {"start_year": "comic_vine", "total_issues": "comic_vine"}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_aplicador_ignora_obra_referencia_y_plan_caducado():
    assert URL is not None
    engine = create_async_engine(url_asyncpg(URL))
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with fabrica() as db, db.begin():
            serie = _serie(start_year=None, total_issues=None)
            db.add(serie)
            await db.flush()
            db.add(EntitySourceRecord(
                entity_type="series", entity_id=serie.id,
                source="comic_vine", external_id="4050",
                payload={"normalizado": {"edition_scope": {
                    "start_year": 1963, "total_issues": 544}}},
                payload_hash="h2", license="CV",
            ))
            await db.flush()
            contexto = await cargar_contexto(db, serie.id)
            plan = contexto.plan()
            assert not plan.cambios_aplicables()
            actual = await db.get(Series, serie.id)
            actual.start_year = 1985
            await db.flush()
            with pytest.raises(PlanCaducadoError):
                await Aplicador(db).aplicar(plan)
    finally:
        await engine.dispose()
