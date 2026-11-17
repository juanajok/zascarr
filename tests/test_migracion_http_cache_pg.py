# ruff: noqa: E501
"""Migración 0037 (`http_cache`) y repositorio `CacheHttp` contra Postgres real (AC-08/AC-09).

Se salta sin `TEST_DATABASE_URL`. Usa una BD efímera (`tests._pg.bd_efimera`) y verifica el
tramo `0036 → head` (tabla, UNIQUE e índices), la vuelta a `0036`, y que el ORM inserta y lee
la fila; después, que `CacheHttp` hace upsert, renueva y purga solo lo caducado.
"""
from __future__ import annotations

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import HttpCache
from zascarr.utils.cache_http import CacheHttp, FilaCache, comprimir_cuerpo, descomprimir_cuerpo

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")

COLUMNAS = {
    "id", "url_hash", "url_canonical", "domain", "status_code", "content_type",
    "is_negative", "etag", "last_modified", "body_zlib", "fetched_at", "fresh_until",
    "retain_until",
}


async def _motor(url: str):
    return create_async_engine(url_asyncpg(url), poolclass=NullPool)


async def _columnas(url: str, tabla: str) -> set[str]:
    motor = await _motor(url)
    try:
        async with motor.begin() as c:
            r = await c.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :t"), {"t": tabla})
            return {fila[0] for fila in r.all()}
    finally:
        await motor.dispose()


async def _existe(url: str, tabla: str) -> bool:
    motor = await _motor(url)
    try:
        async with motor.begin() as c:
            r = await c.execute(text("SELECT to_regclass(:t)"), {"t": f"public.{tabla}"})
            return r.scalar_one() is not None
    finally:
        await motor.dispose()


async def _indices(url: str, tabla: str) -> set[str]:
    motor = await _motor(url)
    try:
        async with motor.begin() as c:
            r = await c.execute(text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = :t"), {"t": tabla})
            return {fila[0] for fila in r.all()}
    finally:
        await motor.dispose()


async def _unicos(url: str, tabla: str) -> set[str]:
    motor = await _motor(url)
    try:
        async with motor.begin() as c:
            r = await c.execute(text(
                "SELECT constraint_name FROM information_schema.table_constraints "
                "WHERE table_schema = 'public' AND table_name = :t "
                "AND constraint_type = 'UNIQUE'"), {"t": tabla})
            return {fila[0] for fila in r.all()}
    finally:
        await motor.dispose()


async def _version(url: str) -> str:
    motor = await _motor(url)
    try:
        async with motor.begin() as c:
            r = await c.execute(text("SELECT version_num FROM alembic_version"))
            return r.scalar_one()
    finally:
        await motor.dispose()


def _cabeza() -> str:
    """La revisión `head` de las migraciones (no se fija a mano: crece con el proyecto)."""
    return alembic(URL, "heads").stdout.split()[0]


class TestMigracionHttpCache:
    async def test_0037_crea_tabla_con_unique_e_indices_y_se_revierte(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "0036")
            assert not await _existe(url, "http_cache")

            alembic(url, "upgrade", "head")
            assert await _columnas(url, "http_cache") >= COLUMNAS
            assert "uq_http_cache_url_hash" in await _unicos(url, "http_cache")
            indices = await _indices(url, "http_cache")
            assert {"ix_http_cache_domain", "ix_http_cache_retain_until"} <= indices
            assert await _version(url) == _cabeza()

            # El ORM mapea exactamente la tabla: inserta y lee la misma fila.
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            ahora = datetime.now(UTC)
            try:
                async with fabrica() as sesion:
                    sesion.add(HttpCache(
                        url_hash="a" * 64, url_canonical="https://dc.fandom.com/api.php",
                        domain="dc.fandom.com", status_code=200,
                        content_type="application/json", is_negative=False,
                        etag='"e1"', last_modified=None, body_zlib=b"datos",
                        fetched_at=ahora, fresh_until=ahora + timedelta(hours=24),
                        retain_until=ahora + timedelta(days=15)))
                    await sesion.commit()
                async with fabrica() as sesion:
                    fila = (await sesion.execute(
                        select(HttpCache).where(HttpCache.url_hash == "a" * 64)
                    )).scalar_one()
                    assert fila.domain == "dc.fandom.com"
                    assert fila.etag == '"e1"' and fila.body_zlib == b"datos"
                    assert fila.is_negative is False
            finally:
                await motor.dispose()

            alembic(url, "downgrade", "0036")
            assert not await _existe(url, "http_cache")
            assert await _version(url) == "0036"


class TestCacheHttpPg:
    async def test_escribir_leer_renovar_upsert_y_purgar(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            fabrica = async_sessionmaker(motor, expire_on_commit=False)
            try:
                repo = CacheHttp(fabrica)
                ahora = datetime.now(UTC)
                cuerpo = comprimir_cuerpo(b'{"ok":true}')
                fila = FilaCache(
                    url_hash="h" * 64, url_canonical="https://dc.fandom.com/api.php",
                    domain="dc.fandom.com", status_code=200,
                    content_type="application/json", is_negative=False, etag='"e1"',
                    last_modified=None, body_zlib=cuerpo, fetched_at=ahora,
                    fresh_until=ahora + timedelta(hours=24),
                    retain_until=ahora + timedelta(days=15))
                await repo.escribir(fila)
                leida = await repo.leer("h" * 64)
                assert leida is not None and leida.etag == '"e1"'
                assert descomprimir_cuerpo(leida.body_zlib) == b'{"ok":true}'

                # Upsert: la misma url_hash actualiza, no duplica.
                negativa = replace(fila, status_code=404, is_negative=True,
                                   body_zlib=None, fresh_until=ahora, retain_until=ahora)
                await repo.escribir(negativa)
                actualizada = await repo.leer("h" * 64)
                assert actualizada.is_negative and actualizada.body_zlib is None
                assert actualizada.status_code == 404

                assert await repo.renovar(
                    "h" * 64, fetched_at=ahora,
                    fresh_until=ahora + timedelta(hours=1),
                    retain_until=ahora + timedelta(days=1)) == 1
                assert await repo.renovar(
                    "inexistente".ljust(64, "0"), fetched_at=ahora,
                    fresh_until=ahora, retain_until=ahora) == 0

                # La purga borra solo lo que ya pasó `retain_until` (nunca por `fresh_until`).
                caducada = replace(fila, url_hash="v" * 64,
                                   retain_until=ahora - timedelta(seconds=1))
                vigente = replace(fila, url_hash="n" * 64,
                                  retain_until=ahora + timedelta(days=1))
                await repo.escribir(caducada)
                await repo.escribir(vigente)
                assert await repo.purgar(ahora) == 1
                assert await repo.leer("v" * 64) is None
                assert await repo.leer("n" * 64) is not None
            finally:
                await motor.dispose()
