# ruff: noqa: E501
"""Migración 0036 (Fandom): columnas de identidad por wiki, aditiva y reversible.

Se salta sin `TEST_DATABASE_URL` (Postgres real). Verifica el tramo que abrió el hueco
detectado al desplegar: de `0035` (sin columnas) a `head` (con columnas y UNIQUE) y vuelta.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def columnas(url: str, tabla: str) -> set[str]:
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    try:
        async with motor.begin() as c:
            r = await c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"), {"t": tabla})
            return {fila[0] for fila in r.all()}
    finally:
        await motor.dispose()


async def version(url: str) -> str:
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    try:
        async with motor.begin() as c:
            r = await c.execute(text("SELECT version_num FROM alembic_version"))
            return r.scalar_one()
    finally:
        await motor.dispose()


def cabeza() -> str:
    """La revisión `head` de las migraciones (no se fija a mano: crece con el proyecto)."""
    return alembic(URL, "heads").stdout.split()[0]


class TestMigracionFandom:
    async def test_0036_anade_columnas_y_se_puede_revertir(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "0035")
            sin_columnas = {"fandom_dc_slug", "fandom_marvel_slug"}
            for tabla in ("series", "issues"):
                assert not (sin_columnas & await columnas(url, tabla))

            alembic(url, "upgrade", "head")
            for tabla in ("series", "issues"):
                assert sin_columnas <= await columnas(url, tabla)
            assert await version(url) == cabeza()

            alembic(url, "downgrade", "0035")
            for tabla in ("series", "issues"):
                assert not (sin_columnas & await columnas(url, tabla))
