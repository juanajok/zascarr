"""Criterio 4 sobre PostgreSQL real: clasificación y candado, sin escanear."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    AltaEstado,
    AltaOperacion,
    AsignacionEstado,
    AsignacionOperacion,
    ComicTradition,
    File,
    FileFormat,
    ImportRun,
    Series,
    VinculacionOperacion,
)
from zascarr.services.operaciones import resumen_operaciones

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


async def _sembrar(url: str):
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    ahora = datetime.now(UTC)
    ids = {}
    async with fab() as s:
        serie = Series(id=uuid.uuid4(), title="Serie 123b", tradition=ComicTradition.AMERICAN)
        s.add(serie)
        await s.flush()
        for n, estado in enumerate(
            (
                AsignacionEstado.PREPARADA,
                AsignacionEstado.CONFIRMADA,
                AsignacionEstado.LIMPIADA,
                AsignacionEstado.CANCELADA,
            ),
            start=1,
        ):
            f = File(
                id=uuid.uuid4(),
                file_path=f"/tmp/123b/{n}.cbz",
                file_name=f"{n}.cbz",
                file_format=FileFormat.CBZ,
            )
            s.add(f)
            await s.flush()
            op = AsignacionOperacion(
                id=uuid.uuid4(),
                file_id=f.id,
                series_id=serie.id,
                estado=estado,
                origen=f"/tmp/123b/{n}.cbz",
                destino=f"/tmp/123b/dest-{n}.cbz",
                temporal=f"/tmp/123b/.dest-{n}.part",
                size_bytes=1,
                mtime_ns=1,
                sha256="a" * 64,
                issue_number=str(n),
                formato="single_issue",
            )
            s.add(op)
            ids[estado.value] = op.id
        s.add_all(
            [
                AltaOperacion(
                    operacion_id=uuid.uuid4(),
                    series_id=serie.id,
                    estado=AltaEstado.CREADA,
                    token_hasta=ahora + timedelta(hours=1),
                ),
                AltaOperacion(
                    operacion_id=uuid.uuid4(),
                    series_id=serie.id,
                    estado=AltaEstado.DESHECHA,
                    token_hasta=ahora + timedelta(hours=1),
                ),
            ]
        )
        for global_ in ("vinculados_todos", "vinculados_parcialmente", "nada_vinculado"):
            s.add(
                VinculacionOperacion(
                    operacion_id=uuid.uuid4(),
                    series_id=serie.id,
                    resultado={"version": 1, "global": global_, "archivos": [], "totales": {}},
                    token_hasta=ahora + timedelta(hours=1),
                )
            )
        s.add_all(
            [
                ImportRun(started_at=ahora, finished_at=ahora, error_count=0, details={}),
                ImportRun(
                    started_at=ahora, finished_at=ahora, error_count=1, details={"errors": ["x"]}
                ),
            ]
        )
        await s.commit()
    await motor.dispose()
    return ids


@pytest.mark.asyncio
async def test_resumen_clasifica_las_cuatro_tablas_sin_escanear(url_bd, monkeypatch):
    await _sembrar(url_bd)
    monkeypatch.setattr(Path, "rglob", lambda *_: (_ for _ in ()).throw(AssertionError("rglob")))
    monkeypatch.setattr(
        Path, "iterdir", lambda *_: (_ for _ in ()).throw(AssertionError("iterdir"))
    )
    monkeypatch.setattr(os, "walk", lambda *_: (_ for _ in ()).throw(AssertionError("walk")))

    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    fab = async_sessionmaker(motor, expire_on_commit=False)
    try:
        async with fab() as s:
            r = await resumen_operaciones(s)
    finally:
        await motor.dispose()
    assert r["asignacion"] == {
        "completada": 1,
        "en_curso": 0,
        "recuperable": 2,
        "fallida": 1,
        "desconocida": 0,
        "total": 4,
    }
    assert r["alta"] == {"completada": 1, "no_aplica": 1, "desconocida": 0, "total": 2}
    assert r["vinculacion"] == {
        "completada": 1,
        "parcial": 1,
        "sin_efecto": 1,
        "desconocida": 0,
        "total": 3,
    }
    assert r["import_runs"]["completada"] == 1 and r["import_runs"]["con_errores"] == 1
    assert r["no_persistidas"]["registro"]["persistido"] is False


@pytest.mark.asyncio
async def test_el_candado_consultivo_marca_en_curso(url_bd):
    ids = await _sembrar(url_bd)
    op = ids["preparada"]
    clave = op.int & 0x7FFF_FFFF_FFFF_FFFF
    motor = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    candado = await motor.connect()
    trans = await candado.begin()
    try:
        assert (
            await candado.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": clave})
        ).scalar() is True
        fab = async_sessionmaker(motor, expire_on_commit=False)
        async with fab() as s:
            r = await resumen_operaciones(s)
        assert r["asignacion"]["en_curso"] == 1
        assert r["asignacion"]["recuperable"] == 1
    finally:
        await trans.rollback()
        await candado.close()
        await motor.dispose()
