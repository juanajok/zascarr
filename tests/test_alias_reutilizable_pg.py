# ruff: noqa: E501
"""MIT-M7 132-a sobre PostgreSQL real: migración, ciclo, matcher y efectos."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import alembic, bd_efimera_sync, migrar_a_head, url_asyncpg
from tests.test_revision_carpetas_pg import Banco
from zascarr.core.matcher import SeriesMatcher
from zascarr.models import (
    ComicTradition,
    EstadoAlias,
    LocalAlias,
    OrigenAlias,
    Series,
)
from zascarr.services.alias_reutilizable import (
    AliasConflictoError,
    AliasRetiradoError,
    activar_aprendido,
    activar_importado,
    cambiar_importado,
    crear_importado,
    desactivar_aprendido,
    desactivar_importado,
    historial_aprendido,
    listar_importados,
    retirar_aprendido,
    retirar_importado,
)
from zascarr.services.review import ReviewService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd):
    banco = Banco(url_bd)
    await banco.limpiar()
    yield SimpleNamespace(banco=banco)
    await banco.cerrar()


async def _serie(entorno, titulo="Batman"):
    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title=titulo, tradition=ComicTradition.AMERICAN))
        await s.commit()
    return sid


@pytest.mark.asyncio
async def test_ciclo_alias_aprendido_y_historial_pg(entorno):
    sid = await _serie(entorno)
    async with entorno.banco.fabrica() as s:
        alias = LocalAlias(pattern_norm="batman", series_id=sid,
                           origen=OrigenAlias.APRENDIDO, estado=EstadoAlias.PROPUESTO,
                           version=1, historial=[])
        s.add(alias)
        await s.commit()
        aid = alias.id
    async with entorno.banco.fabrica() as s:
        a = await activar_aprendido(s, aid)
        assert a.estado is EstadoAlias.ACTIVO and a.version == 2
        a = await desactivar_aprendido(s, aid)
        assert a.estado is EstadoAlias.DESACTIVADO and a.version == 3
        a = await retirar_aprendido(s, aid)
        assert a.estado is EstadoAlias.RETIRADO and a.version == 4
        with pytest.raises(AliasRetiradoError):
            await activar_aprendido(s, aid)
        assert [e["motivo"] for e in await historial_aprendido(s, aid)] == [
            "activacion", "desactivacion", "retirada"]


@pytest.mark.asyncio
async def test_learning_crea_propuesto_no_activo_pg(entorno):
    sid = await _serie(entorno)
    async with entorno.banco.fabrica() as s:
        await ReviewService(s)._learn_alias("Batman 001.cbz", sid)
        await s.commit()
        a = (await s.execute(select(LocalAlias))).scalar_one()
        assert a.estado is EstadoAlias.PROPUESTO and a.version == 1
        assert a.historial[0]["motivo"] == "aprendizaje"


@pytest.mark.asyncio
async def test_matcher_solo_usa_activo_pg(entorno):
    sid = await _serie(entorno)
    async with entorno.banco.fabrica() as s:
        s.add(LocalAlias(pattern_norm="batman", series_id=sid,
                         estado=EstadoAlias.PROPUESTO, version=1))
        await s.commit()
        assert await SeriesMatcher(s).find_alias("Batman") is None
        (await s.execute(select(LocalAlias))).scalar_one().estado = EstadoAlias.ACTIVO
        await s.commit()
        hit = await SeriesMatcher(s).find_alias("Batman")
        assert hit is not None and hit.series_id == sid


@pytest.mark.asyncio
async def test_alias_importado_crud_y_unicidad_pg(entorno):
    sid, sid2 = await _serie(entorno), await _serie(entorno, "Otra")
    async with entorno.banco.fabrica() as s:
        a = await crear_importado(s, patron="Batman", series_id=sid,
                                  scope_path="Comics/Batman")
        aid = a.alias_id
        assert a.estado is EstadoAlias.PROPUESTO and a.version == 1
        a = await activar_importado(s, aid)
        assert a.estado is EstadoAlias.ACTIVO and a.version == 2
        with pytest.raises(AliasConflictoError):
            b = await crear_importado(s, patron="Batman", series_id=sid2,
                                      scope_path="Comics/Batman")
            await activar_importado(s, b.alias_id)
        a = await desactivar_importado(s, aid)
        assert a.estado is EstadoAlias.DESACTIVADO
        a = await activar_importado(s, aid)
        a = await cambiar_importado(s, aid, series_id=sid2)
        assert a.series_id == sid2 and a.version == 5
        a = await retirar_importado(s, aid)
        assert a.estado is EstadoAlias.RETIRADO
        with pytest.raises(AliasRetiradoError):
            await activar_importado(s, aid)
        assert len(await listar_importados(s, incluir_historial=True)) == 7


@pytest.mark.asyncio
async def test_sin_efectos_en_series_archivos_pg(entorno):
    sid = await _serie(entorno)
    async with entorno.banco.fabrica() as s:
        a = await crear_importado(s, patron="Batman", series_id=sid)
        await activar_importado(s, a.alias_id)
        assert (await s.execute(text("SELECT count(*) FROM series"))).scalar_one() == 1
        assert (await s.execute(text("SELECT count(*) FROM files"))).scalar_one() == 0


def test_backfill_0026_desde_0025():
    with bd_efimera_sync(URL) as url:
        alembic(url, "upgrade", "0025")

        async def _sembrar():
            from sqlalchemy.ext.asyncio import create_async_engine
            motor = create_async_engine(url_asyncpg(url))
            try:
                async with motor.begin() as c:
                    sid, aid = uuid4(), uuid4()
                    await c.execute(text("INSERT INTO series (id,title,tradition) VALUES (:s,'Batman','american')"), {"s": sid})
                    await c.execute(text("INSERT INTO local_aliases (id,pattern_norm,series_id) VALUES (:a,'batman',:s)"), {"a": aid, "s": sid})
            finally:
                await motor.dispose()
        asyncio.run(_sembrar())
        migrar_a_head(url)

        async def _comprobar():
            from sqlalchemy.ext.asyncio import create_async_engine
            motor = create_async_engine(url_asyncpg(url))
            try:
                async with motor.connect() as c:
                    row = (await c.execute(text(
                        "SELECT estado,version,origen,historial FROM local_aliases"))).one()
                    assert row.estado == "propuesto" and row.version == 1 and row.origen == "aprendido"
                    assert row.historial[0]["motivo"] == "migracion"
            finally:
                await motor.dispose()
        asyncio.run(_comprobar())
