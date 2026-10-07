# ruff: noqa: E501
"""Migración 0018 (`alta_operaciones`, rebanada 2b): esquema, estados, independencia de la serie y bajada — Postgres real.

Cada prueba trabaja en una BD efímera propia. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import RAIZ, alembic, bd_efimera, entorno_para_alembic, url_asyncpg

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def consultar(url: str, sql: str, **p):
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    try:
        async with motor.begin() as c:
            r = await c.execute(text(sql), p)
            return r.all() if r.returns_rows else []
    finally:
        await motor.dispose()


async def version(url: str) -> str:
    return (await consultar(url, "SELECT version_num FROM alembic_version"))[0][0]


async def existe(url: str) -> tuple[bool, bool]:
    t = (await consultar(url, "SELECT to_regclass('alta_operaciones') IS NOT NULL"))[0][0]
    ty = (await consultar(url, "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'alta_estado')"))[0][0]
    return t, ty


INSERT = ("INSERT INTO alta_operaciones (operacion_id, series_id, estado, token_hasta) VALUES "
          "(CAST(:o AS uuid), CAST(:s AS uuid), CAST(:e AS alta_estado), now() + make_interval(mins => :m))")


class TestEsquema:

    async def test_la_0018_cuelga_de_la_0017_y_sube_sin_tocar_nada_mas(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "0017")
            assert await existe(url) == (False, False)
            antes = await consultar(url, "SELECT count(*) FROM series")
            alembic(url, "upgrade", "0018")
            assert await version(url) == "0018" and await existe(url) == (True, True)
            assert await consultar(url, "SELECT count(*) FROM series") == antes
            alembic(url, "upgrade", "head")                                        # idempotente
            assert await existe(url) == (True, True)

    async def test_columnas_clave_estados_e_indice(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            cols = {r[0]: (r[1], r[2]) for r in await consultar(
                url, "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'alta_operaciones'")}
            assert cols == {"operacion_id": ("uuid", "NO"), "series_id": ("uuid", "NO"), "estado": ("USER-DEFINED", "NO"),
                            "token_hasta": ("timestamp with time zone", "NO"), "creada": ("timestamp with time zone", "NO"),
                            "actualizada": ("timestamp with time zone", "NO")}
            assert [r[0] for r in await consultar(url, "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
                                                       "WHERE t.typname = 'alta_estado' ORDER BY enumsortorder")] == ["creada", "deshecha"]
            assert [r[0] for r in await consultar(url, "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
                                                       "AND a.attnum = ANY(i.indkey) WHERE i.indrelid = 'alta_operaciones'::regclass AND i.indisprimary")] == ["operacion_id"]
            assert (await consultar(url, "SELECT count(*) FROM pg_indexes WHERE indexname = 'ix_alta_operaciones_purga'"))[0][0] == 1

    async def test_el_estado_solo_admite_creada_o_deshecha_y_la_operacion_es_unica(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            op, serie = str(uuid4()), str(uuid4())
            await consultar(url, INSERT, o=op, s=serie, e="creada", m=15)
            with pytest.raises(DBAPIError):
                await consultar(url, INSERT, o=op, s=serie, e="deshecha", m=15)       # la misma operación dos veces
            with pytest.raises(DBAPIError):
                await consultar(url, INSERT, o=str(uuid4()), s=serie, e="otro", m=15)

    async def test_series_id_no_es_clave_foranea_y_borrar_la_serie_no_borra_el_comprobante(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            assert (await consultar(url, "SELECT count(*) FROM pg_constraint WHERE conrelid = 'alta_operaciones'::regclass "
                                         "AND contype = 'f'"))[0][0] == 0
            sid, op = str(uuid4()), str(uuid4())
            await consultar(url, "INSERT INTO series (id, title, tradition) VALUES (CAST(:s AS uuid), 'Flash', 'american')", s=sid)
            await consultar(url, INSERT, o=op, s=sid, e="creada", m=15)
            await consultar(url, "DELETE FROM series WHERE id = CAST(:s AS uuid)", s=sid)
            assert (await consultar(url, "SELECT estado::text, series_id::text FROM alta_operaciones"))[0] == ("creada", sid)

    async def test_el_modelo_y_la_migracion_coinciden(self):
        """Sin diferencias entre `AltaOperacion` y lo que crea la migración (en un subproceso: aquí `import alembic`
        resuelve al directorio de migraciones del repo)."""
        import subprocess
        import sys
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            guion = (
                "import asyncio, json\n"
                "from alembic.autogenerate import compare_metadata\n"
                "from alembic.migration import MigrationContext\n"
                "from sqlalchemy.ext.asyncio import create_async_engine\n"
                "from zascarr.database import Base\n"
                "import zascarr.models\n"
                "def comparar(c):\n"
                "    return compare_metadata(MigrationContext.configure(c, opts={'compare_type': True}), Base.metadata)\n"
                "async def main():\n"
                "    m = create_async_engine(__import__('os').environ['DATABASE_URL'])\n"
                "    async with m.connect() as c:\n"
                "        d = await c.run_sync(comparar)\n"
                "    await m.dispose()\n"
                "    print(json.dumps([repr(x) for x in d if 'alta_operaciones' in repr(x) or 'alta_estado' in repr(x)]))\n"
                "asyncio.run(main())\n"
            )
            r = subprocess.run([sys.executable, "-c", guion], cwd=RAIZ, env=entorno_para_alembic(os.environ, url),
                               capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr[-1500:]
            assert r.stdout.strip().splitlines()[-1] == "[]", r.stdout


class TestBajada:
    """Destructiva (se pierden los comprobantes): se NIEGA si queda alguno con el token todavía válido."""

    async def test_sin_comprobantes_baja_y_vuelve_a_subir(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            alembic(url, "downgrade", "0017")
            assert await version(url) == "0017" and await existe(url) == (False, False)
            alembic(url, "upgrade", "head")
            assert await existe(url) == (True, True)

    @pytest.mark.parametrize("estado", ["creada", "deshecha"])
    async def test_con_un_token_vigente_se_niega_y_no_pierde_nada(self, estado):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            await consultar(url, INSERT, o=str(uuid4()), s=str(uuid4()), e=estado, m=10)
            r = alembic(url, "downgrade", "0017", estricto=False)
            assert r.returncode != 0 and "token todavía válido" in r.stderr
            assert await version(url) == "0018" and await existe(url) == (True, True)
            assert (await consultar(url, "SELECT estado::text FROM alta_operaciones"))[0][0] == estado

    async def test_con_los_tokens_ya_caducados_baja(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            await consultar(url, INSERT, o=str(uuid4()), s=str(uuid4()), e="deshecha", m=-5)
            alembic(url, "downgrade", "0017")
            assert await existe(url) == (False, False)

    async def test_una_confirmacion_durante_la_bajada_la_hace_negarse(self):
        """Contar y borrar no pueden estar separados por una inserción ajena: la bajada toma `ACCESS EXCLUSIVE` antes."""
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            try:
                async with motor.connect() as c:
                    tx = await c.begin()
                    await c.execute(text(INSERT), dict(o=str(uuid4()), s=str(uuid4()), e="creada", m=10))   # sin commit
                    bajada = asyncio.create_task(asyncio.to_thread(alembic, url, "downgrade", "0017", estricto=False))
                    await asyncio.sleep(2)
                    assert not bajada.done()                                         # espera al bloqueo de la inserción
                    await tx.commit()
                r = await asyncio.wait_for(bajada, 60)
            finally:
                await motor.dispose()
            assert r.returncode != 0 and "token todavía válido" in r.stderr
            assert await version(url) == "0018" and (await consultar(url, "SELECT count(*) FROM alta_operaciones"))[0][0] == 1
