"""Regresión Postgres de los cuatro estados de `checks.database` (E6).

`_database_status` distingue unreachable / migration_required /
schema_incompatible / ok. Sin Postgres real no se puede probar (el resto de la
suite es deliberadamente sin BD); se salta sin TEST_DATABASE_URL, mismo patrón
que `test_title_norm.py` y `test_huecos_pg.py`:

    docker run --rm -d --name zascarr_test_pg -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=zascarr -p 15433:5432 postgres:15-alpine
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:15433/zascarr \\
        pytest tests/test_health_db_pg.py

No destructivo: cada caso crea un esquema temporal dentro de una transacción que
SIEMPRE se revierte; no toca `public` ni exige que la BD esté migrada.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.api.health import _alembic_head, _database_status

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)

_ESQUEMA = "zascarr_health_test"
_DOMAIN_TABLES = ("series", "issues", "files", "wishlist")
_HEAD = _alembic_head()


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _exigir_bd_de_prueba(session) -> None:
    nombre = (await session.execute(text("SELECT current_database()"))).scalar()
    if not nombre or "test" not in nombre.lower():
        raise RuntimeError(
            f"TEST_DATABASE_URL apunta a «{nombre}» (sin 'test'); se niega a ejecutarse."
        )


@pytest.fixture
async def db():
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


async def _montar(db, head: str | None, tablas: tuple[str, ...]) -> None:
    """Esquema temporal + `alembic_version` en `head` (None = sin tabla) + stubs."""
    await db.execute(text(f"CREATE SCHEMA {_ESQUEMA}"))
    await db.execute(text(f"SET search_path TO {_ESQUEMA}"))
    if head is not None:
        await db.execute(text("CREATE TABLE alembic_version (version_num varchar(32))"))
        await db.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:h)"), {"h": head}
        )
    for tabla in tablas:
        await db.execute(text(f"CREATE TABLE {tabla} (id int)"))


class TestDatabaseStatusPg:

    @pytest.mark.asyncio
    async def test_ok(self, db):
        await _montar(db, _HEAD, _DOMAIN_TABLES)
        estado, _ = await _database_status(db)
        assert estado == "ok"

    @pytest.mark.asyncio
    async def test_migration_required_sin_tabla_de_versiones(self, db):
        await _montar(db, None, _DOMAIN_TABLES)  # sin alembic_version → nunca migrado
        estado, _ = await _database_status(db)
        assert estado == "migration_required"

    @pytest.mark.asyncio
    async def test_migration_required_version_desfasada(self, db):
        await _montar(db, "0000", _DOMAIN_TABLES)  # version_num ≠ head
        estado, _ = await _database_status(db)
        assert estado == "migration_required"

    @pytest.mark.asyncio
    async def test_schema_incompatible(self, db):
        await _montar(db, _HEAD, ("series", "issues", "files"))  # falta wishlist
        estado, _ = await _database_status(db)
        assert estado == "schema_incompatible"

    @pytest.mark.asyncio
    async def test_unreachable(self):
        engine = create_async_engine("postgresql+asyncpg://nadie:nada@127.0.0.1:1/nada")
        sesion = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with sesion() as session:
                estado, _ = await _database_status(session)
        finally:
            await engine.dispose()
        assert estado == "unreachable"
