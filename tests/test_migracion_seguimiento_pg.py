"""#993: migraciones 0047+0048 (seguimiento) aditivas y reversibles (Postgres real)."""
from __future__ import annotations

import asyncio
import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic, bd_efimera_sync, migrar_a_head, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _consultar_sync(url: str, sql: str):
    async def _run():
        motor = create_async_engine(url_asyncpg(url))
        try:
            async with motor.begin() as c:
                r = await c.execute(text(sql))
                return r.all() if r.returns_rows else []
        finally:
            await motor.dispose()
    return asyncio.run(_run())


def test_columnas_enum_tabla_e_indice_y_downgrade():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        columnas = _consultar_sync(url,
            "SELECT column_name, data_type, is_nullable FROM information_schema.columns "
            "WHERE table_name='series' AND column_name IN "
            "('follow_new_issues','follow_new_issues_since') ORDER BY 1")
        assert [(c[0], c[1], c[2]) for c in columnas] == [
            ("follow_new_issues", "boolean", "NO"),
            ("follow_new_issues_since", "timestamp with time zone", "YES"),
        ]
        enum = _consultar_sync(url,
            "SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid "
            "WHERE t.typname='wishlist_origen' ORDER BY e.enumsortorder")
        assert "seguimiento" in [fila[0] for fila in enum]
        tabla = _consultar_sync(url,
            "SELECT to_regclass('public.seguimiento_vistos')")
        assert tabla and tabla[0][0] is not None
        indice = _consultar_sync(url,
            "SELECT indexdef FROM pg_indexes WHERE indexname='uq_wishlist_seguimiento_numero'")
        # El predicado no puede nombrar el valor de enum nuevo en la misma
        # transacción: cubre politica+seguimiento excluyendo manual.
        assert indice and "WHERE" in indice[0][0] and "manual" in indice[0][0]

        alembic(url, "downgrade", "0046")
        assert _consultar_sync(url,
            "SELECT column_name FROM information_schema.columns WHERE table_name='series' "
            "AND column_name LIKE 'follow_new_issues%'") == []
        assert _consultar_sync(url, "SELECT to_regclass('public.seguimiento_vistos')")[0][0] is None
