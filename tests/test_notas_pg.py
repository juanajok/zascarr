"""#342/BL-WK4: notas contra Postgres real (crear/editar/borrar y XSS se guarda crudo)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import ComicTradition, Issue, Note, Series
from zascarr.services.notas import (
    NotaInvalidaError,
    borrar_numero,
    borrar_serie,
    guardar_numero,
    guardar_serie,
    leer_serie,
    notas_de_serie,
)

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


async def _montar(db):
    serie = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    db.add(serie)
    issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1", title="La maga")
    db.add(issue)
    await db.flush()
    return serie, issue


@pytest.mark.asyncio
async def test_crear_editar_leer_y_borrar(db):
    serie, issue = await _montar(db)
    nota = await guardar_serie(db, serie.id, "  falta el mapa  ")
    assert nota.texto == "falta el mapa"
    assert (await leer_serie(db, serie.id)).texto == "falta el mapa"

    await guardar_serie(db, serie.id, "<script>alert(1)</script>")
    assert (await leer_serie(db, serie.id)).texto == "<script>alert(1)</script>"

    nota_num = await guardar_numero(db, issue.id, "páginas 12-13")
    assert nota_num.texto == "páginas 12-13"
    serie_nota, numeros = await notas_de_serie(db, serie.id)
    assert serie_nota.texto == "<script>alert(1)</script>"
    assert len(numeros) == 1 and numeros[0][0].texto == "páginas 12-13"

    assert await borrar_serie(db, serie.id) is True
    assert await borrar_serie(db, serie.id) is False
    assert await borrar_numero(db, issue.id) is True
    assert await leer_serie(db, serie.id) is None


@pytest.mark.asyncio
async def test_idempotente_y_validacion(db):
    serie, _issue = await _montar(db)
    await guardar_serie(db, serie.id, "uno")
    await guardar_serie(db, serie.id, "dos")
    assert (await leer_serie(db, serie.id)).texto == "dos"
    with pytest.raises(NotaInvalidaError):
        await guardar_serie(db, serie.id, "   ")


@pytest.mark.asyncio
async def test_check_exactamente_una_entidad(db):
    serie, issue = await _montar(db)
    db.add(Note(series_id=serie.id, issue_id=issue.id, texto="x"))
    with pytest.raises(IntegrityError):
        await db.flush()


@pytest.mark.asyncio
async def test_migracion_0027_subida_y_bajada():
    from tests._pg import alembic, bd_efimera, migrar_a_head
    async with bd_efimera(TEST_DATABASE_URL) as url:
        migrar_a_head(url)
        engine = create_async_engine(_url_asyncpg(url))
        async with engine.connect() as conexion:
            existe = (await conexion.execute(text(
                "SELECT to_regclass('public.notes')"))).scalar()
            assert existe is not None
        await engine.dispose()
        alembic(url, "downgrade", "0026")
        engine = create_async_engine(_url_asyncpg(url))
        async with engine.connect() as conexion:
            existe = (await conexion.execute(text(
                "SELECT to_regclass('public.notes')"))).scalar()
            assert existe is None
        await engine.dispose()
        alembic(url, "upgrade", "head")
