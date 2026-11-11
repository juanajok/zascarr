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
    ConflictoVersionError,
    cambiar_decision,
    estado_de_coleccion,
    ids_por_estado,
    marcar_no_completar,
    version_de_decision,
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


async def _serie(db, tmp_path, titulo, total, fuente, numeros, *, no_completar=False,
                 publisher=None):
    pub = publisher or Publisher(id=uuid4(), name=f"Editorial {uuid4().hex}")
    if publisher is None:
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


@pytest.mark.asyncio
async def test_filtro_sql_paginado_misma_query(db, tmp_path):
    pub = Publisher(id=uuid4(), name=f"Editorial paginada {uuid4().hex}")
    db.add(pub)
    for i in range(3):
        await _serie(db, tmp_path, f"Paginada {i}", 2,
                     MetadataSource.COMIC_VINE.value, [1, 2], publisher=pub)
    decidida = await _serie(db, tmp_path, "Paginada decidida", 9,
                            MetadataSource.COMIC_VINE.value, [1],
                            no_completar=True, publisher=pub)
    from zascarr.services.series import SeriesService
    servicio = SeriesService(db)
    p1, total, pagina = await servicio.list_series_paginado(
        page=1, page_size=2, publisher_id=pub.id, coleccion=COMPLETA)
    p2, total2, pagina2 = await servicio.list_series_paginado(
        page=2, page_size=2, publisher_id=pub.id, coleccion=COMPLETA)
    assert (total, total2, pagina, pagina2) == (3, 3, 1, 2)
    ids1, ids2 = {s.id for s in p1}, {s.id for s in p2}
    assert len(ids1) == 2 and len(ids2) == 1 and not (ids1 & ids2)
    assert decidida.id not in ids1 | ids2


@pytest.mark.asyncio
async def test_update_jsonb_version_obsoleta_es_409(db, tmp_path):
    serie = await _serie(db, tmp_path, "Concurrente", 3,
                         MetadataSource.COMIC_VINE.value, [1])
    assert version_de_decision(serie) == 0
    v1 = await cambiar_decision(db, serie.id, no_completar=True, version_esperada=0)
    assert v1 == 1
    with pytest.raises(ConflictoVersionError):
        await cambiar_decision(db, serie.id, no_completar=True, version_esperada=0)
    await db.refresh(serie)
    assert version_de_decision(serie) == 1
    assert serie.metadata_["coleccion"]["no_completar"] is True
    v2 = await cambiar_decision(db, serie.id, no_completar=False, version_esperada=1)
    assert v2 == 2
