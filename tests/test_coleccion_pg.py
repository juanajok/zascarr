"""#340/BL-WK2 contra Postgres real: estados, filtro y resumen."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    MetadataSource,
    Publisher,
    Series,
    WishlistPolicy,
)
from zascarr.services.coleccion import (
    COMPLETA,
    FALTAN,
    NO_CALCULABLE,
    NO_COMPLETAR,
    estado_de_coleccion,
    ids_por_estado,
    marcar_no_completar,
)
from zascarr.services.resumen import resumen_biblioteca

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


@pytest.fixture
async def db():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        nombre = (await session.execute(text("SELECT current_database()"))).scalar()
        if not nombre or "test" not in nombre.lower():
            raise RuntimeError(f"TEST_DATABASE_URL apunta a «{nombre}»; se niega.")
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


async def _serie(db, tmp_path, titulo, total, fuente, numeros, *, no_completar=False):
    pub = Publisher(id=uuid4(), name=f"Editorial {uuid4().hex}")
    db.add(pub)
    serie = Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN,
                   start_year=1980, publisher_id=pub.id, total_issues=total,
                   metadata_source=fuente, wishlist_policy=WishlistPolicy.NONE)
    if no_completar:
        marcar_no_completar(serie)
    db.add(serie)
    for numero in numeros:
        issue = Issue(id=uuid4(), series_id=serie.id, issue_number=str(numero),
                      format=IssueFormat.SINGLE_ISSUE, sort_order=float(numero))
        db.add(issue)
        ruta = tmp_path / f"{serie.id}-{numero}.cbz"
        ruta.write_bytes(b"x")
        db.add(File(id=uuid4(), issue_id=issue.id, file_path=str(ruta),
                    file_name=ruta.name, file_format=FileFormat.CBZ,
                    file_size_bytes=1, is_missing=False))
    await db.flush()
    return serie


@pytest.mark.asyncio
async def test_estados_y_filtro(db, tmp_path):
    completa = await _serie(db, tmp_path, "Completa", 2, MetadataSource.COMIC_VINE.value, [1, 2])
    faltan = await _serie(db, tmp_path, "Faltan", 5, MetadataSource.COMIC_VINE.value, [1])
    no_calc = await _serie(db, tmp_path, "NoCalc", 10, MetadataSource.ANILIST.value, [1])
    decidida = await _serie(db, tmp_path, "Decidida", 3, MetadataSource.COMIC_VINE.value, [1],
                            no_completar=True)

    assert (await estado_de_coleccion(db, completa)).tipo == COMPLETA
    assert (await estado_de_coleccion(db, faltan)).tipo == FALTAN
    assert (await estado_de_coleccion(db, no_calc)).tipo == NO_CALCULABLE
    assert (await estado_de_coleccion(db, decidida)).tipo == NO_COMPLETAR

    # La BD de pruebas puede compartir filas de otras pruebas: se comprueba la
    # pertenencia de las sembradas, no la igualdad global.
    assert completa.id in await ids_por_estado(db, COMPLETA)
    assert faltan.id in await ids_por_estado(db, FALTAN)
    assert no_calc.id in await ids_por_estado(db, NO_CALCULABLE)
    assert decidida.id in await ids_por_estado(db, NO_COMPLETAR)
    assert decidida.id not in await ids_por_estado(db, FALTAN)


@pytest.mark.asyncio
async def test_resumen_no_cuenta_los_huecos_de_no_completar(db, tmp_path):
    await _serie(db, tmp_path, "Completa", 2, MetadataSource.COMIC_VINE.value, [1, 2])
    await _serie(db, tmp_path, "Faltan", 5, MetadataSource.COMIC_VINE.value, [1])
    await _serie(db, tmp_path, "Decidida", 30, MetadataSource.COMIC_VINE.value, [1],
                 no_completar=True)

    r = await resumen_biblioteca(db)
    assert r.huecos_pendientes >= 4          # incluye la serie «Faltan»; la decidida no suma
    assert r.series_no_completar >= 1
    assert r.series_con_recuento >= 2


@pytest.mark.asyncio
async def test_filtro_biblioteca_combinado_en_sql(db, tmp_path):
    completa = await _serie(db, tmp_path, "Alpha Completa", 2,
                           MetadataSource.COMIC_VINE.value, [1, 2])
    faltan = await _serie(db, tmp_path, "Beta Faltan", 5,
                          MetadataSource.COMIC_VINE.value, [1])
    from zascarr.services.series import SeriesService
    items, total, _ = await SeriesService(db).list_series_paginado(
        page=1, page_size=10, coleccion_ids={faltan.id})
    assert total == 1 and [s.id for s in items] == [faltan.id]
    items, total, _ = await SeriesService(db).list_series_paginado(
        page=1, page_size=10, coleccion_ids={completa.id})
    assert total == 1 and [s.id for s in items] == [completa.id]
