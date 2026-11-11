"""Alta de publicación sin número: Issue NULL + enlace de archivo (ADR 0016)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    Series,
    SeriesKind,
)
from zascarr.services.especiales import EspecialesService, EspecialSinNumeroError

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def sesion(url_bd):
    engine = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    fabrica = async_sessionmaker(engine, expire_on_commit=False)
    async with fabrica() as s:
        yield s
    await engine.dispose()


async def _mundo(sesion):
    serie = Series(id=uuid4(), title=f"Serie especial {uuid4().hex[:6]}",
                   tradition=ComicTradition.AMERICAN, kind=SeriesKind.REGULAR)
    archivo = File(id=uuid4(), file_path=f"/tmp/{uuid4().hex}.cbz",
                   file_name="Bad Weekend - Criminal.cbr", file_format=FileFormat.CBR)
    sesion.add_all([serie, archivo])
    await sesion.commit()
    return serie, archivo


async def test_crea_issue_null_y_enlaza_sin_mover_archivo(sesion):
    serie, archivo = await _mundo(sesion)
    servicio = EspecialesService(sesion)

    issue = await servicio.vincular_especial(
        archivo.id, serie.id, "Bad Weekend", IssueFormat.GRAPHIC_NOVEL)
    await sesion.commit()

    assert issue.issue_number is None
    assert issue.title == "Bad Weekend"
    assert issue.format == IssueFormat.GRAPHIC_NOVEL
    assert issue.metadata_["sin_numero"] is True

    await sesion.refresh(archivo)
    assert archivo.issue_id == issue.id
    assert archivo.file_path == f"/tmp/{archivo.file_path.rsplit('/', 1)[-1]}"
    assert archivo.metadata_["match_status"] == "manual_especial"


async def test_permite_varios_especiales_sin_numero_en_la_misma_serie(sesion):
    serie, archivo1 = await _mundo(sesion)
    archivo2 = File(id=uuid4(), file_path=f"/tmp/{uuid4().hex}.cbr",
                    file_name="Lobo - Año 1.cbz", file_format=FileFormat.CBZ)
    sesion.add(archivo2)
    await sesion.commit()
    servicio = EspecialesService(sesion)

    i1 = await servicio.vincular_especial(archivo1.id, serie.id, "Bad Weekend")
    i2 = await servicio.vincular_especial(archivo2.id, serie.id, "Año 1")
    await sesion.commit()

    filas = (await sesion.execute(
        select(Issue).where(Issue.series_id == serie.id,
                            Issue.issue_number.is_(None)))).scalars().all()
    assert len(filas) == 2
    assert {i.id for i in filas} == {i1.id, i2.id}


async def test_rechaza_numero_inventado_y_archivo_ya_enlazado(sesion):
    serie, archivo = await _mundo(sesion)
    servicio = EspecialesService(sesion)
    with pytest.raises(EspecialSinNumeroError):
        await servicio.vincular_especial(
            archivo.id, serie.id, "Bad Weekend", IssueFormat.SINGLE_ISSUE)
    await servicio.vincular_especial(archivo.id, serie.id, "Bad Weekend")
    await sesion.commit()
    with pytest.raises(EspecialSinNumeroError):
        await servicio.vincular_especial(archivo.id, serie.id, "Otro")
