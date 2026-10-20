"""Desglose de lo registrado del Inicio (`services/inicio.py`) sobre Postgres real.

Las pruebas con FakeSession comprueban la plantilla y el SQL compilado; aquí se comprueba que la consulta de
`FILTER (WHERE …)` cuenta de verdad cada parte, que las partes suman el total y que «por revisar» es el número
de la lista (`ReviewService.count_pending`). Se saltan sin `TEST_DATABASE_URL`.
"""
# ruff: noqa: E501
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import ComicTradition, File, FileFormat, ImportRun, Issue, Series
from zascarr.services.inicio import Desglose, copias_descartadas, desglose_registrados
from zascarr.services.review import ReviewService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def fabrica(url_bd):
    motor = create_async_engine(url_asyncpg(url_bd))
    async with motor.begin() as c:
        await c.execute(text("TRUNCATE files, issues, series, import_runs CASCADE"))
    yield async_sessionmaker(motor, expire_on_commit=False)
    await motor.dispose()


def archivo(nombre: str, *, estado: str | None = "unsorted", issue_id=None, descartado=False,
            ausente=False) -> File:
    return File(id=uuid4(), file_path=f"/biblioteca/{nombre}", file_name=nombre, file_format=FileFormat.CBZ,
                metadata_={"match_status": estado} if estado else {}, issue_id=issue_id,
                review_dismissed=descartado, is_missing=ausente)


@pytest.mark.asyncio
async def test_cada_registrado_cae_en_una_parte_y_por_revisar_es_la_lista(fabrica):
    async with fabrica() as s:
        serie = Series(id=uuid4(), title="Mortadelo y Filemón", tradition=ComicTradition.TEBEO)
        s.add(serie)
        await s.flush()
        numero = Issue(id=uuid4(), series_id=serie.id, issue_number="1")
        s.add(numero)
        await s.flush()
        s.add_all([
            archivo("clasificado 1.cbz", estado="direct", issue_id=numero.id),
            archivo("clasificado 2.cbz", estado="direct", issue_id=numero.id),
            archivo("por revisar 1.cbz"), archivo("por revisar 2.cbz"), archivo("por revisar 3.cbz"),
            archivo("serie sin numero.cbz", estado="direct"),
            archivo("sin estado.cbz", estado=None),          # filas antiguas sin match_status
            archivo("descartado.cbz", descartado=True),
            archivo("ausente por revisar.cbz", ausente=True),
            archivo("ausente clasificado.cbz", estado="direct", issue_id=numero.id, ausente=True),
        ])
        await s.commit()

    async with fabrica() as s:
        d = await desglose_registrados(s)
        lista = await ReviewService(s).count_pending()

    assert d == Desglose(total=8, clasificados=2, por_revisar_presentes=3, descartados=1,
                         por_revisar_ausentes=1)
    assert d.sin_numero == 2
    assert sum(n for n, _, _ in d.partes) == d.total
    assert d.por_revisar == lista == 4


@pytest.mark.asyncio
async def test_sin_archivos_todo_es_cero(fabrica):
    async with fabrica() as s:
        assert await desglose_registrados(s) == Desglose()
        assert await copias_descartadas(s) == 0


@pytest.mark.asyncio
async def test_las_copias_descartadas_son_las_del_ultimo_registro_no_las_del_informe(fabrica):
    ahora = datetime.now(UTC)

    def corrida(dias: int, copias: int, **details) -> ImportRun:
        cuando = ahora - timedelta(days=dias)
        return ImportRun(started_at=cuando, finished_at=cuando, files_scanned=1542,
                         duplicate_count=copias, details=details)

    async with fabrica() as s:
        s.add_all([
            corrida(9, 300, kind="adoption"),
            corrida(2, 217, kind="adoption"),
            # Más recientes, pero un informe de duplicados (cuenta grupos, no copias) y un ciclo de descargas.
            corrida(1, 99, kind="audit"),
            corrida(0, 1),
        ])
        await s.commit()
    async with fabrica() as s:
        assert await copias_descartadas(s) == 217
