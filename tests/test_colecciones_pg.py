"""#155/BL-D6: colecciones, política efectiva y orquestador (Postgres real)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import (
    Collection,
    CollectionAutoSearch,
    ComicTradition,
    File,
    FileFormat,
    Issue,
    IssueFormat,
    LegalAcknowledgment,
    MetadataSource,
    Series,
    Wishlist,
    WishlistOrigin,
    WishlistPolicy,
    WishlistStatus,
)
from zascarr.services.colecciones import (
    asignar_serie,
    borrar_coleccion,
    crear_coleccion,
    detalle_coleccion,
    editar_coleccion,
    listar_colecciones,
    quitar_serie,
    series_sin_coleccion,
)
from zascarr.services.legal import current_legal_version
from zascarr.services.orchestrator import Orchestrator
from zascarr.services.politica import politica_efectiva, querer_de_serie

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="requiere TEST_DATABASE_URL")


def _url(url: str) -> str:
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


@pytest.fixture
async def db():
    engine = create_async_engine(_url(TEST_DATABASE_URL or ""))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        nombre = (await session.execute(text("SELECT current_database()"))).scalar()
        if "test" not in (nombre or "").lower():
            raise RuntimeError("TEST_DATABASE_URL debe apuntar a una base de pruebas")
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


async def aceptar(db) -> None:
    db.add(LegalAcknowledgment(id=uuid4(), legal_version=current_legal_version()))
    await db.flush()


async def serie(db, titulo="Flash", *, policy=WishlistPolicy.NONE, total=3,
                collection=None) -> Series:
    s = Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN,
               total_issues=total, metadata_source=MetadataSource.COMIC_VINE.value,
               wishlist_policy=policy, collection_id=collection.id if collection else None)
    db.add(s)
    await db.flush()
    return s


async def presente(db, s: Series, numero="1") -> Issue:
    i = Issue(id=uuid4(), series_id=s.id, issue_number=numero, format=IssueFormat.SINGLE_ISSUE)
    db.add(i)
    await db.flush()
    db.add(File(id=uuid4(), issue_id=i.id, file_path=f"/lib/{uuid4()}.cbz",
                file_name="x.cbz", file_format=FileFormat.CBZ, is_missing=False))
    await db.flush()
    return i


async def test_politica_efectiva_hereda_incluye_y_excluye(db):
    c_heredar = await crear_coleccion(db, name="Hereda", description="",
                                      auto_search=CollectionAutoSearch.HEREDAR.value)
    c_incluir = await crear_coleccion(db, name="Incluye", description="",
                                      auto_search=CollectionAutoSearch.INCLUIR.value)
    c_excluir = await crear_coleccion(db, name="Excluye", description="",
                                      auto_search=CollectionAutoSearch.EXCLUIR.value)
    s_heredar = await serie(db, "Hereda", policy=WishlistPolicy.MISSING,
                            collection=c_heredar.coleccion)
    s_incluir = await serie(db, "Incluye", policy=WishlistPolicy.NONE,
                            collection=c_incluir.coleccion)
    s_excluir = await serie(db, "Excluye", policy=WishlistPolicy.MISSING,
                            collection=c_excluir.coleccion)
    s_sin = await serie(db, "Sin", policy=WishlistPolicy.MISSING)
    assert await politica_efectiva(db, s_heredar) == WishlistPolicy.MISSING
    assert await politica_efectiva(db, s_incluir) == WishlistPolicy.MISSING
    assert await politica_efectiva(db, s_excluir) == WishlistPolicy.NONE
    assert await politica_efectiva(db, s_sin) == WishlistPolicy.MISSING
    # incluir genera faltantes aunque la guardada sea «ninguno»
    await presente(db, s_incluir)
    assert await querer_de_serie(
        db, s_incluir, politica=await politica_efectiva(db, s_incluir)) == \
        await querer_de_serie(db, s_incluir, politica=WishlistPolicy.MISSING)


async def test_crud_nombre_unico_case_insensitive_y_asignacion_unica(db):
    r = await crear_coleccion(db, name="  Grapas  ", description="En curso",
                              auto_search="heredar")
    assert r.ok and r.coleccion.name == "Grapas"
    dup = await crear_coleccion(db, name="grapas", description="", auto_search="heredar")
    assert not dup.ok and "name" in dup.errores
    s = await serie(db, "Flash")
    assert (await listar_colecciones(db))[0].name == "Grapas"
    assert not (await asignar_serie(db, r.coleccion.id, s.id)).errores
    assert s.collection_id == r.coleccion.id
    detalle = await detalle_coleccion(db, r.coleccion.id)
    assert detalle is not None and len(detalle.series) == 1
    fila = detalle.series[0]
    assert fila.wishlist_policy_label == "No buscar automáticamente"
    assert fila.politica_efectiva_label == "No buscar automáticamente"
    assert str(s.id) not in {x.id for x in await series_sin_coleccion(db)}
    assert not (await asignar_serie(db, r.coleccion.id, s.id)).ok
    assert await quitar_serie(db, r.coleccion.id, s.id)
    assert s.collection_id is None
    await editar_coleccion(db, r.coleccion.id, name="Clásicos", description="",
                           auto_search="excluir")
    assert (await db.get(Collection, r.coleccion.id)).auto_search == CollectionAutoSearch.EXCLUIR


async def test_borrar_coleccion_deja_series_sin_coleccion(db):
    r = await crear_coleccion(db, name="Temporal", description="", auto_search="heredar")
    s = await serie(db, "Flash", collection=r.coleccion)
    assert await borrar_coleccion(db, r.coleccion.id)
    await db.flush()
    await db.refresh(s)
    assert s.collection_id is None


async def test_orquestador_incluye_faltantes_y_no_toca_manuales(db):
    await aceptar(db)
    c = await crear_coleccion(db, name="Incluye", description="", auto_search="incluir")
    s = await serie(db, "Flash", policy=WishlistPolicy.NONE, total=3, collection=c.coleccion)
    await presente(db, s)
    manual = Wishlist(id=uuid4(), series_id=s.id, numero=99, origen=WishlistOrigin.MANUAL,
                      status=WishlistStatus.WANTED)
    db.add(manual)
    await db.flush()
    antes = {(i.numero, i.origen, i.status) for i in (await db.execute(
        select(Wishlist).where(Wishlist.series_id == s.id))).scalars()}
    await Orchestrator(db).sync_policy_items(lote=10)
    await db.flush()
    despues = list((await db.execute(select(Wishlist).where(
        Wishlist.series_id == s.id, Wishlist.origen == WishlistOrigin.POLICY))).scalars())
    assert {w.numero for w in despues} == {2, 3}
    assert antes <= {(i.numero, i.origen, i.status) for i in (await db.execute(
        select(Wishlist).where(Wishlist.series_id == s.id))).scalars()}


async def test_orquestador_excluye_y_retira_solo_politica(db):
    await aceptar(db)
    c = await crear_coleccion(db, name="Excluye", description="", auto_search="excluir")
    s = await serie(db, "Flash", policy=WishlistPolicy.MISSING, total=3, collection=c.coleccion)
    policy = Wishlist(id=uuid4(), series_id=s.id, numero=2, origen=WishlistOrigin.POLICY,
                      status=WishlistStatus.WANTED)
    manual = Wishlist(id=uuid4(), series_id=s.id, numero=3, origen=WishlistOrigin.MANUAL,
                      status=WishlistStatus.WANTED)
    db.add_all([policy, manual])
    await db.flush()
    await Orchestrator(db).sync_policy_items(lote=10)
    await db.flush()
    assert policy.status == WishlistStatus.RETIRADO
    assert manual.status == WishlistStatus.WANTED
    assert (await db.execute(select(Wishlist).where(
        Wishlist.series_id == s.id, Wishlist.origen == WishlistOrigin.POLICY,
        Wishlist.status == WishlistStatus.WANTED))).first() is None


async def test_ficha_usa_la_politica_efectiva_y_explica_la_coleccion(db):
    from zascarr.web.series import _contexto_politica
    await aceptar(db)
    c_inc = await crear_coleccion(db, name="Incluye", description="", auto_search="incluir")
    s_inc = await serie(db, "Flash", policy=WishlistPolicy.NONE, total=3,
                        collection=c_inc.coleccion)
    await presente(db, s_inc)
    ctx_inc = await _contexto_politica(db, s_inc)
    assert ctx_inc["politica_actual"] == WishlistPolicy.NONE
    assert ctx_inc["politica_efectiva"] == WishlistPolicy.MISSING
    assert ctx_inc["veredicto"]["tipo"] != "ninguno"
    assert ctx_inc["politica_actual_etiqueta"] == "No buscar automáticamente"
    assert ctx_inc["politica_efectiva_etiqueta"] == "Buscar los números que faltan"
    assert "Incluye" in (ctx_inc["coleccion_causa"] or "")
    c_exc = await crear_coleccion(db, name="Excluye", description="", auto_search="excluir")
    s_exc = await serie(db, "Batman", policy=WishlistPolicy.MISSING, total=3,
                        collection=c_exc.coleccion)
    ctx_exc = await _contexto_politica(db, s_exc)
    assert ctx_exc["politica_actual"] == WishlistPolicy.MISSING
    assert ctx_exc["politica_efectiva"] == WishlistPolicy.NONE
    assert ctx_exc["veredicto"]["tipo"] == "ninguno"
    assert "Excluye" in (ctx_exc["coleccion_causa"] or "")
