"""Migración 0041: raíz por defecto, tradiciones y backfill (#156, corte A)."""
from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import alembic, bd_efimera, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def _con(url):
    return create_async_engine(url_asyncpg(url))


async def _scalar(url, sql, **params):
    engine = await _con(url)
    try:
        async with engine.connect() as c:
            return (await c.execute(text(sql), params)).scalar_one()
    finally:
        await engine.dispose()


async def _filas(url, sql, **params):
    engine = await _con(url)
    try:
        async with engine.connect() as c:
            return (await c.execute(text(sql), params)).all()
    finally:
        await engine.dispose()


async def _sembrar_0040(url):
    engine = await _con(url)
    try:
        async with engine.begin() as c:
            await c.execute(text(
                "INSERT INTO files (id, file_path, file_name, file_format) VALUES "
                "(gen_random_uuid(), '/media/library/a.cbz', 'a.cbz', 'cbz'), "
                "(gen_random_uuid(), '/media/library/sub/b.cbz', 'b.cbz', 'cbz'), "
                "(gen_random_uuid(), '/media/library2/c.cbz', 'c.cbz', 'cbz'), "
                "(gen_random_uuid(), '/otra/d.cbz', 'd.cbz', 'cbz')"
            ))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upgrade_0041_crea_raiz_tradiciones_y_backfill(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRARY_PATH", "/media/library")
    monkeypatch.setenv("HOST_LIBRARY_DIR", "/srv/library")
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "0040")
        await _sembrar_0040(url)
        antes = dict(await _filas(url, "SELECT file_path, sha256_hash FROM files"))
        alembic(url, "upgrade", "0041")
        raiz = (await _filas(
            url, "SELECT id, name, path, host_path, enabled, is_default FROM library_roots"
        ))[0]
        assert raiz[1:] == ("Biblioteca", "/media/library", "/srv/library", True, True)
        tradiciones = {
            r[0] for r in await _filas(
                url, "SELECT tradition::text FROM library_root_traditions")
        }
        assert tradiciones == {"american", "franco_belgian", "manga", "tebeo", "fumetti",
                               "manhwa", "manhua", "british", "other"}
        filas = await _filas(url, "SELECT file_path, root_id FROM files ORDER BY file_path")
        por_ruta = {r[0]: r[1] for r in filas}
        assert por_ruta["/media/library/a.cbz"] == raiz[0]
        assert por_ruta["/media/library/sub/b.cbz"] == raiz[0]
        assert por_ruta["/media/library2/c.cbz"] is None
        assert por_ruta["/otra/d.cbz"] is None
        despues = dict(await _filas(url, "SELECT file_path, sha256_hash FROM files"))
        assert antes == despues
        # Operaciones: columnas nullable y sin backfill inventado.
        for tabla in ("asignacion_operaciones", "apartado_operaciones"):
            assert await _scalar(
                url, f"SELECT count(*) FROM {tabla} WHERE root_id IS NOT NULL") == 0
        assert await _scalar(url, "SELECT version_num FROM alembic_version") == "0041"


@pytest.mark.asyncio
async def test_downgrade_0041_sin_datos_revierte_todo(monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", "/media/library")
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "0040")
        await _sembrar_0040(url)
        alembic(url, "upgrade", "0041")
        alembic(url, "downgrade", "0040")
        assert await _scalar(
            url,
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name IN ('library_roots','library_root_traditions')",
        ) == 0
        columnas = {r[0] for r in await _filas(
            url, "SELECT column_name FROM information_schema.columns "
                 "WHERE table_name IN ('files','asignacion_operaciones','apartado_operaciones') "
                 "AND column_name = 'root_id'")}
        assert columnas == set()
        assert await _scalar(url, "SELECT count(*) FROM files "
                                  "WHERE file_path = '/media/library2/c.cbz'") == 1


@pytest.mark.asyncio
async def test_downgrade_falla_cerrado_con_dos_raices(monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", "/media/library")
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "0041")
        engine = await _con(url)
        try:
            async with engine.begin() as c:
                await c.execute(text(
                    "INSERT INTO library_roots (name, path, enabled, is_default) "
                    "VALUES ('Segunda', '/media/library2', true, false)"
                ))
        finally:
            await engine.dispose()
        resultado = alembic(url, "downgrade", "0040", estricto=False)
        assert resultado.returncode != 0
        assert "más de una raíz" in resultado.stderr


@pytest.mark.asyncio
async def test_restricciones_de_raiz_y_tradicion(monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", "/media/library")
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "0041")
        engine = await _con(url)
        try:
            async with engine.begin() as c:
                with pytest.raises(IntegrityError):
                    await c.execute(text(
                        "INSERT INTO library_roots (name, path, enabled, is_default) "
                        "VALUES ('Otra', '/media/library', true, false)"
                    ))
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_constraints_del_contrato(monkeypatch):
    monkeypatch.setenv("LIBRARY_PATH", "/media/library")
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "0041")
        engine = await _con(url)
        try:
            for sql in (
                "INSERT INTO library_roots (name, path) VALUES ('Biblioteca', '/media/library2')",
                "INSERT INTO library_roots (name, path, is_default) "
                "VALUES ('Otra', '/media/library2', true)",
                "INSERT INTO library_roots (name, path) VALUES ('Biblioteca', '/media/otra')",
            ):
                try:
                    async with engine.begin() as c:
                        await c.execute(text(sql))
                except IntegrityError:
                    pass
                else:
                    raise AssertionError(f"la restricción no rechazó: {sql}")
            async with engine.begin() as c:
                root_id = (await c.execute(text("SELECT id FROM library_roots"))).scalar_one()
                await c.execute(text(
                    "INSERT INTO files (id, file_path, file_name, file_format, root_id) "
                    "VALUES (gen_random_uuid(), '/media/library/x.cbz', 'x.cbz', 'cbz', :r)"
                ), {"r": root_id})
            with pytest.raises(IntegrityError):
                async with engine.begin() as c:
                    await c.execute(text("DELETE FROM library_roots WHERE id = :r"), {"r": root_id})
        finally:
            await engine.dispose()
