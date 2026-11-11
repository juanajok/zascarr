"""Migración 0027: `Series.kind` y `Series.parent_series_id` (solo anuales).

Se ejecuta sobre una BD efímera con Postgres real. Sin `TEST_DATABASE_URL` se
salta: la suite normal no necesita base de datos para esta pieza.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def consultar(url: str, sql: str, **params):
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    try:
        async with motor.begin() as conexion:
            resultado = await conexion.execute(text(sql), params)
            return resultado.all() if resultado.returns_rows else []
    finally:
        await motor.dispose()


async def columnas(url: str) -> set[str]:
    filas = await consultar(url, """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'series'
    """)
    return {fila[0] for fila in filas}


async def test_0027_es_aditiva_y_no_convierte_las_series_existentes_en_anuales():
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "0026")
        await consultar(url, """
            INSERT INTO series (id, title, tradition)
            VALUES (gen_random_uuid(), 'Batman Vol 1', 'american')
        """)

        alembic(url, "upgrade", "head")

        filas = await consultar(url, """
            SELECT title, kind::text, parent_series_id FROM series
        """)
        assert filas == [("Batman Vol 1", "regular", None)]


async def test_0027_permite_la_serie_anual_enlazada_al_padre_y_protege_el_ciclo():
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "head")
        await consultar(url, """
            INSERT INTO series (id, title, tradition)
            VALUES ('00000000-0000-0000-0000-000000000001', 'Batman', 'american')
        """)
        await consultar(url, """
            INSERT INTO series (id, title, tradition, kind, parent_series_id)
            VALUES ('00000000-0000-0000-0000-000000000002', 'Batman Annual',
                    'american', 'annual',
                    '00000000-0000-0000-0000-000000000001')
        """)

        fila = (await consultar(url, """
            SELECT kind::text, parent_series_id FROM series
            WHERE title = 'Batman Annual'
        """))[0]
        assert fila[0] == "annual"
        assert str(fila[1]) == "00000000-0000-0000-0000-000000000001"

        with pytest.raises(IntegrityError):
            await consultar(url, """
                UPDATE series SET parent_series_id = id
                WHERE title = 'Batman Annual'
            """)


async def test_0027_el_downgrade_quita_columnas_y_tipo():
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "head")
        assert {"kind", "parent_series_id"} <= await columnas(url)

        alembic(url, "downgrade", "0026")

        assert not ({"kind", "parent_series_id"} & await columnas(url))
        tipos = await consultar(url, """
            SELECT 1 FROM pg_type WHERE typname = 'series_kind'
        """)
        assert tipos == []
