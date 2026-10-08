# ruff: noqa: E501
"""Migración 0019 (`vinculacion_operaciones`, rebanada 2d): esquema, inmutabilidad, independencia de la serie y bajada.

Cada prueba trabaja en una BD efímera propia. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import asyncio
import json
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

INSERT = ("INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta) VALUES "
          "(CAST(:o AS uuid), CAST(:s AS uuid), CAST(:r AS jsonb), now() + make_interval(mins => :m))")


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


async def objetos(url: str) -> dict[str, bool]:
    return {
        "tabla": (await consultar(url, "SELECT to_regclass('vinculacion_operaciones') IS NOT NULL"))[0][0],
        "funcion": (await consultar(url, "SELECT EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'vinculacion_operaciones_inmutable')"))[0][0],
        "disparador": (await consultar(url, "SELECT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'trg_vinculacion_operaciones_inmutable')"))[0][0],
        "indice": (await consultar(url, "SELECT EXISTS (SELECT 1 FROM pg_indexes WHERE indexname = 'ix_vinculacion_operaciones_purga')"))[0][0],
    }


def cabeza() -> str:
    return alembic(URL, "heads").stdout.split()[0]


TODO = {"tabla": True, "funcion": True, "disparador": True, "indice": True}
NADA = {k: False for k in TODO}


class TestEsquema:

    async def test_la_0019_cuelga_de_la_0018_y_sube_sin_tocar_nada_mas(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "0018")
            assert await objetos(url) == NADA
            alembic(url, "upgrade", "0019")
            assert await version(url) == "0019" and await objetos(url) == TODO
            alembic(url, "upgrade", "head")                                        # idempotente
            assert await objetos(url) == TODO and cabeza() == "0019"

    async def test_columnas_clave_e_indice(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            cols = {r[0]: (r[1], r[2]) for r in await consultar(
                url, "SELECT column_name, data_type, is_nullable FROM information_schema.columns WHERE table_name = 'vinculacion_operaciones'")}
            assert cols == {"operacion_id": ("uuid", "NO"), "series_id": ("uuid", "NO"), "resultado": ("jsonb", "NO"),
                            "token_hasta": ("timestamp with time zone", "NO"), "creada": ("timestamp with time zone", "NO")}
            assert [r[0] for r in await consultar(url, "SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
                                                       "AND a.attnum = ANY(i.indkey) WHERE i.indrelid = 'vinculacion_operaciones'::regclass AND i.indisprimary")] == ["operacion_id"]

    async def test_la_operacion_es_unica_y_series_id_no_es_clave_foranea(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            op, serie = str(uuid4()), str(uuid4())
            await consultar(url, INSERT, o=op, s=serie, r="{}", m=15)
            with pytest.raises(DBAPIError):
                await consultar(url, INSERT, o=op, s=serie, r="{}", m=15)
            assert (await consultar(url, "SELECT count(*) FROM pg_constraint WHERE conrelid = 'vinculacion_operaciones'::regclass AND contype = 'f'"))[0][0] == 0
            sid = str(uuid4())
            await consultar(url, "INSERT INTO series (id, title, tradition) VALUES (CAST(:s AS uuid), 'Flash', 'american')", s=sid)
            await consultar(url, INSERT, o=str(uuid4()), s=sid, r="{}", m=15)
            await consultar(url, "DELETE FROM series WHERE id = CAST(:s AS uuid)", s=sid)
            assert (await consultar(url, "SELECT count(*) FROM vinculacion_operaciones WHERE series_id = CAST(:s AS uuid)", s=sid))[0][0] == 1

    async def test_el_modelo_y_la_migracion_coinciden(self):
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
                "    print(json.dumps([repr(x) for x in d if 'vinculacion_operaciones' in repr(x)]))\n"
                "asyncio.run(main())\n"
            )
            r = subprocess.run([sys.executable, "-c", guion], cwd=RAIZ, env=entorno_para_alembic(os.environ, url),
                               capture_output=True, text=True, timeout=120)
            assert r.returncode == 0, r.stderr[-1500:]
            assert r.stdout.strip().splitlines()[-1] == "[]", r.stdout


class TestInmutabilidad:

    async def test_el_disparador_rechaza_cualquier_update_y_permite_el_delete(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            op = str(uuid4())
            await consultar(url, INSERT, o=op, s=str(uuid4()), r=json.dumps({"a": 1}), m=15)
            for sql in ("UPDATE vinculacion_operaciones SET resultado = '{}'::jsonb",
                        "UPDATE vinculacion_operaciones SET series_id = gen_random_uuid()",
                        "UPDATE vinculacion_operaciones SET token_hasta = now()",
                        "UPDATE vinculacion_operaciones SET resultado = resultado"):
                with pytest.raises(DBAPIError, match="inmutable"):
                    await consultar(url, sql)
            assert (await consultar(url, "SELECT resultado FROM vinculacion_operaciones"))[0][0] == {"a": 1}
            await consultar(url, "DELETE FROM vinculacion_operaciones")
            assert (await consultar(url, "SELECT count(*) FROM vinculacion_operaciones"))[0][0] == 0


class TestBajada:
    """Destructiva: se NIEGA si queda algún informe con el token todavía válido; retira todo coherentemente."""

    async def test_sin_informes_baja_retira_todo_y_vuelve_a_subir(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            alembic(url, "downgrade", "0018")
            assert await version(url) == "0018" and await objetos(url) == NADA          # tabla, función, disparador e índice
            alembic(url, "upgrade", "head")
            assert await objetos(url) == TODO

    async def test_con_un_token_vigente_se_niega_y_conserva_todo(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            await consultar(url, INSERT, o=str(uuid4()), s=str(uuid4()), r="{}", m=10)
            r = alembic(url, "downgrade", "0018", estricto=False)
            assert r.returncode != 0 and "token todavía válido" in r.stderr
            assert await version(url) == "0019" and await objetos(url) == TODO
            assert (await consultar(url, "SELECT count(*) FROM vinculacion_operaciones"))[0][0] == 1

    async def test_con_los_tokens_ya_caducados_baja(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            await consultar(url, INSERT, o=str(uuid4()), s=str(uuid4()), r="{}", m=-5)
            alembic(url, "downgrade", "0018")
            assert await objetos(url) == NADA

    async def test_bajar_dos_versiones_atraviesa_la_0019_y_la_0018(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            alembic(url, "downgrade", "0017")
            assert await version(url) == "0017"
            alembic(url, "upgrade", "head")
            assert await version(url) == "0019" and await objetos(url) == TODO

    async def test_una_insercion_durante_la_bajada_la_hace_negarse(self):
        async with bd_efimera(URL) as url:
            alembic(url, "upgrade", "head")
            motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
            try:
                async with motor.connect() as c:
                    tx = await c.begin()
                    await c.execute(text(INSERT), dict(o=str(uuid4()), s=str(uuid4()), r="{}", m=10))      # sin commit
                    bajada = asyncio.create_task(asyncio.to_thread(alembic, url, "downgrade", "0018", estricto=False))
                    await asyncio.sleep(2)
                    assert not bajada.done()
                    await tx.commit()
                r = await asyncio.wait_for(bajada, 60)
            finally:
                await motor.dispose()
            assert r.returncode != 0 and "token todavía válido" in r.stderr
            assert await version(url) == "0019" and (await consultar(url, "SELECT count(*) FROM vinculacion_operaciones"))[0][0] == 1
