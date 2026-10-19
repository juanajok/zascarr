# ruff: noqa: E501
"""Migración 0020 (#239 / ADR 0013): las instalaciones con uso previo conservan sus fuentes activas; las nuevas, no.

Cada prueba trabaja en una BD efímera. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

CLAVES = {"comicvine_enabled", "anilist_enabled", "tebeosfera_enabled", "gcd_enabled"}
TODAS_ACTIVAS = {c: True for c in CLAVES}


async def consultar(url: str, sql: str, **p):
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    try:
        async with motor.begin() as c:
            r = await c.execute(text(sql), p)
            return r.all() if r.returns_rows else []
    finally:
        await motor.dispose()


async def valores(url: str) -> dict:
    v = (await consultar(url, 'SELECT "values" FROM runtime_settings WHERE id = 1'))[0][0]
    return v if isinstance(v, dict) else json.loads(v)


async def version(url: str) -> str:
    return (await consultar(url, "SELECT version_num FROM alembic_version"))[0][0]


async def a_la_0019(url: str) -> None:
    alembic(url, "upgrade", "0019")
    assert await version(url) == "0019"


def subir(url: str) -> None:
    alembic(url, "upgrade", "head")


class TestInstalacionNueva:

    async def test_una_instalacion_nueva_no_escribe_nada(self):
        """bootstrap.sh migra hasta `head` sobre tablas vacías: nace con el default de código (apagadas)."""
        async with bd_efimera(URL) as url:
            subir(url)
            assert await version(url) == "0020" and await valores(url) == {}

    async def test_la_actualizacion_de_una_instalacion_vacia_y_sin_ajustes_tampoco(self):
        async with bd_efimera(URL) as url:
            await a_la_0019(url)
            subir(url)
            assert await valores(url) == {}


class TestInstalacionConUso:

    @pytest.mark.parametrize("sql,motivo", [
        ("INSERT INTO series (id, title, tradition) VALUES (gen_random_uuid(), 'Flash', 'american')", "una serie"),
        ("INSERT INTO import_runs (id, started_at, finished_at) VALUES (gen_random_uuid(), now(), now())", "un ciclo del importador"),
        ("INSERT INTO legal_acknowledgments (legal_version) VALUES ('x')", "la aceptación legal"),
        ("UPDATE runtime_settings SET \"values\" = '{\"prowlarr_enabled\": true}'::jsonb WHERE id = 1", "un ajuste guardado que no es de fuentes"),
    ], ids=["serie", "import_run", "aceptacion-legal", "otro-ajuste"])
    async def test_con_uso_previo_se_escriben_las_cuatro_activas(self, sql, motivo):
        async with bd_efimera(URL) as url:
            await a_la_0019(url)
            await consultar(url, sql)
            subir(url)
            v = await valores(url)
            assert {c: v.get(c) for c in CLAVES} == TODAS_ACTIVAS, f"no se conservaron activas con {motivo}: {v}"

    async def test_no_pisa_lo_que_el_coleccionista_ya_guardo(self):
        async with bd_efimera(URL) as url:
            await a_la_0019(url)
            await consultar(url, "INSERT INTO series (id, title, tradition) VALUES (gen_random_uuid(), 'Flash', 'american')")
            await consultar(url, "UPDATE runtime_settings SET \"values\" = '{\"tebeosfera_enabled\": false, \"prowlarr_url\": \"http://p\"}'::jsonb WHERE id = 1")
            subir(url)
            v = await valores(url)
            assert v["tebeosfera_enabled"] is False, "se pisó una fuente que el coleccionista había apagado"
            assert v["prowlarr_url"] == "http://p"
            assert (v["comicvine_enabled"], v["anilist_enabled"], v["gcd_enabled"]) == (True, True, True)

    async def test_si_falta_la_fila_de_ajustes_la_crea_y_conserva(self):
        async with bd_efimera(URL) as url:
            await a_la_0019(url)
            await consultar(url, "DELETE FROM runtime_settings")
            await consultar(url, "INSERT INTO series (id, title, tradition) VALUES (gen_random_uuid(), 'Flash', 'american')")
            subir(url)
            assert await valores(url) == TODAS_ACTIVAS

    async def test_es_idempotente_y_la_bajada_no_toca_los_ajustes(self):
        async with bd_efimera(URL) as url:
            await a_la_0019(url)
            await consultar(url, "INSERT INTO series (id, title, tradition) VALUES (gen_random_uuid(), 'Flash', 'american')")
            subir(url)
            antes = await valores(url)
            alembic(url, "downgrade", "0019")
            assert await version(url) == "0019" and await valores(url) == antes
            subir(url)
            assert await valores(url) == antes
