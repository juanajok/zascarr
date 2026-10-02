"""«Sigues N series» cuenta SERIES, no peticiones (V4b, revisión de la PR #70) — Postgres real.

`WishlistService.count_active` cuenta filas de Deseados (es lo que lista la pantalla y lo que
muestra el contador del menú). El Inicio decía «Sigues 5 series» con cinco peticiones de tres
series. Aquí se fija el contrato nuevo (`count_active_series`) con peticiones repetidas, por
número y duplicadas, y se comprueba que el contador del menú NO cambia de significado.

Se salta sin TEST_DATABASE_URL (mismo patrón y misma defensa que `test_huecos_pg.py`: transacción
que siempre se revierte y negativa a correr si la base no lleva «test» en el nombre).
"""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from zascarr.models import ComicTradition, Issue, Series, Wishlist, WishlistStatus
from zascarr.services.wishlist import WishlistService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _sql_del_recuento(captura: list) -> str:
    return captura[-1]


class TestSentencia:
    """Sin BD: la forma de la consulta (cuenta DISTINCT, ignora retiradas, resuelve por issue)."""

    @pytest.mark.asyncio
    async def test_cuenta_series_distintas_y_excluye_retiradas(self):
        capturadas = []

        class Sesion:
            async def execute(self, stmt):
                capturadas.append(str(stmt.compile(dialect=postgresql.dialect())))

                class R:
                    def scalar_one(self):
                        return 0
                return R()

        await WishlistService(Sesion()).count_active_series()
        sql = capturadas[0].lower()
        assert "count(distinct(coalesce(wishlist.series_id, issues.series_id)))" in sql
        assert "left outer join issues on issues.id = wishlist.issue_id" in sql
        assert "wishlist.status !=" in sql


pg = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver test_huecos_pg.py",
)


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from tests.test_huecos_pg import _exigir_bd_de_prueba, _url_asyncpg

    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        await _exigir_bd_de_prueba(session)
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


async def _serie(db, titulo):
    s = Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN)
    db.add(s)
    await db.flush()
    return s


async def _issue(db, serie, numero):
    i = Issue(id=uuid4(), series_id=serie.id, issue_number=numero)
    db.add(i)
    await db.flush()
    return i


async def _deseo(db, *, serie=None, issue=None, estado=WishlistStatus.WANTED):
    db.add(Wishlist(id=uuid4(), series_id=serie.id if serie else None,
                    issue_id=issue.id if issue else None, status=estado))
    await db.flush()


@pg
class TestContratoReal:

    @pytest.mark.asyncio
    async def test_varias_peticiones_de_la_misma_serie_cuentan_una_serie(self, db):
        base = await WishlistService(db).count_active_series()
        a, b = await _serie(db, "A"), await _serie(db, "B")
        await _deseo(db, serie=a)
        await _deseo(db, serie=a)            # duplicada exacta
        await _deseo(db, serie=b)
        await _deseo(db, issue=await _issue(db, a, "7"))    # petición por número de A
        await _deseo(db, issue=await _issue(db, b, "3"))    # petición por número de B
        s = WishlistService(db)
        assert await s.count_active_series() - base == 2
        assert await s.count_active() >= 5      # el contador del menú sigue contando peticiones

    @pytest.mark.asyncio
    async def test_las_retiradas_no_cuentan(self, db):
        base = await WishlistService(db).count_active_series()
        a, b = await _serie(db, "A"), await _serie(db, "B")
        await _deseo(db, serie=a)
        await _deseo(db, serie=b, estado=WishlistStatus.RETIRADO)
        assert await WishlistService(db).count_active_series() - base == 1

    @pytest.mark.asyncio
    async def test_la_misma_serie_pedida_por_serie_y_por_numero_es_una(self, db):
        base = await WishlistService(db).count_active_series()
        a = await _serie(db, "A")
        await _deseo(db, serie=a)
        await _deseo(db, issue=await _issue(db, a, "1"))
        assert await WishlistService(db).count_active_series() - base == 1
