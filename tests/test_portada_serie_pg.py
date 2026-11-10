"""BL-INF6 (#592): la elección de portada contra Postgres real.

La suite sin Postgres usa dobles de sesión: no puede comprobar que el JSONB (`metadata["portada"]`)
y el ARRAY (`locked_fields`) se GUARDEN de verdad (SQLAlchemy no sigue mutaciones internas). Aquí se
hace `commit` y se relee la fila. Sin `TEST_DATABASE_URL` se salta, como el resto de pruebas PG.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import ComicTradition, File, FileFormat, Issue, Series
from zascarr.services import portada_serie

URL = os.environ.get("TEST_DATABASE_URL")
PG = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")


@pytest.fixture
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


async def _sembrar(url, *, numeros: int) -> tuple[UUID, UUID, UUID]:
    """(serie, primer issue, primer file): `numeros` números con un CBZ cada uno, desordenados."""
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with fab() as s:
        serie = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                       metadata_={}, locked_fields=[])
        s.add(serie)
        await s.flush()
        issues = []
        for orden in reversed(range(1, numeros + 1)):
            issue = Issue(id=uuid4(), series_id=serie.id, issue_number=str(orden),
                          sort_order=float(orden))
            s.add(issue)
            issues.append(issue)
        await s.flush()
        archivos = []
        for issue in issues:
            f = File(id=uuid4(), issue_id=issue.id,
                     file_path=f"/b/{serie.title}/{issue.issue_number}.cbz",
                     file_name=f"{issue.issue_number}.cbz", file_format=FileFormat.CBZ,
                     file_mtime_ns=123456789)
            s.add(f)
            archivos.append(f)
        await s.commit()
        primero = min(zip(issues, archivos, strict=True), key=lambda par: par[0].sort_order or 0)
    await motor.dispose()
    return serie.id, primero[0].id, primero[1].id


@PG
@pytest.mark.asyncio
async def test_candidatas_pagina_los_numeros_en_orden_de_lectura(url_bd):
    serie_id, primer_issue, _ = await _sembrar(url_bd, numeros=13)
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with fab() as s:
        serie = (await s.execute(select(Series).where(Series.id == serie_id))).scalar_one()
        # Ajustes reales: el panel solo hace `stat` de la caché externa (no existe), así que no
        # escribe ni lee nada del disco de la biblioteca.
        primera = await portada_serie.candidatas_de_portada(s, serie)
    await motor.dispose()

    assert len(primera.numeros) == portada_serie.MAX_CANDIDATAS
    assert [c.origen for c in primera.numeros[:2]] == [
        "Del archivo del nº 1", "Del archivo del nº 2"]
    assert primera.numeros[0].issue_id == primer_issue
    assert primera.hay_mas is True


@PG
@pytest.mark.asyncio
async def test_la_eleccion_persiste_en_jsonb_y_el_lock_en_el_array(url_bd):
    serie_id, _, file_id = await _sembrar(url_bd, numeros=2)
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    async with fab() as s:
        serie = (await s.execute(select(Series).where(Series.id == serie_id))).scalar_one()
        portada_serie.guardar_eleccion(serie, tipo=portada_serie.TIPO_ARCHIVO, file_id=file_id)
        await s.commit()
    async with fab() as s:
        releida = (await s.execute(select(Series).where(Series.id == serie_id))).scalar_one()
        archivo = await portada_serie.archivo_de_portada(s, serie_id, file_id)
    await motor.dispose()

    eleccion = portada_serie.eleccion_de_portada(releida)
    assert eleccion is not None and eleccion["tipo"] == "archivo"
    assert eleccion["file_id"] == str(file_id)
    assert releida.locked_fields == ["cover_url"]
    # El mtime del archivo, con el que la cascada sabe si hay que materializar de nuevo.
    assert archivo and archivo[0][3] == 123456789
