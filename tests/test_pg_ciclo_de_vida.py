# ruff: noqa: E501
"""El ciclo de vida de la BD de pruebas (`tests/_pg.py`) — qué fallaba y por qué.

Tres pruebas de Postgres real fallaban en `main`, y la causa no era de producción:

1. `test_health_db_pg::test_bd_sin_esquema_arranca_y_sirve_solo_diagnostico` exige una BD **sin migrar**
   y todas las demás pruebas de Postgres exigen la **misma** BD **migrada**: incompatibles. Sobre una
   base migrada fallaba con `assert 'ok' == 'migration_required'`; sobre una virgen pasaba y fallaban ~100.
2. y 3. `test_migracion_d8_pg` y `test_migracion_integridad_pg` hacen `alembic downgrade` desde `head`:
   sobre una base sin migrar fallan con «Destination 0014 is not a valid downgrade target», y con la raíz
   del repo en `PYTHONPATH` (lo normal al lanzar `pytest` a mano) el subproceso fallaba con «No module named
   alembic.__main__; 'alembic' is a package and cannot be directly executed» porque `PYTHONSAFEPATH=1`
   no basta si la raíz llega por `PYTHONPATH`.

Las pruebas con `bd_efimera`/`migrar_a_head` necesitan `TEST_DATABASE_URL`; el resto no.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests._pg import (
    RAIZ,
    alembic,
    bd_efimera,
    entorno_para_alembic,
    exigir_nombre_de_prueba,
    migrar_a_head,
    url_asyncpg,
)

URL = os.environ.get("TEST_DATABASE_URL")
necesita_pg = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")
SRC = str(RAIZ / "src")


class TestEntornoDeAlembic:

    def test_quita_la_raiz_del_repo_de_pythonpath_y_conserva_el_resto(self):
        e = entorno_para_alembic({"PYTHONPATH": os.pathsep.join([SRC, str(RAIZ)])}, "postgresql://u:p@h/x_test")
        assert e["PYTHONPATH"] == SRC

    def test_la_raiz_se_reconoce_aunque_se_escriba_distinta(self):
        e = entorno_para_alembic({"PYTHONPATH": f"{RAIZ}{os.sep}.{os.pathsep}{SRC}"}, "postgresql://u:p@h/x_test")
        assert e["PYTHONPATH"] == SRC

    def test_sin_nada_que_conservar_no_deja_pythonpath(self):
        assert "PYTHONPATH" not in entorno_para_alembic({"PYTHONPATH": str(RAIZ)}, "postgresql://u:p@h/x")
        assert "PYTHONPATH" not in entorno_para_alembic({}, "postgresql://u:p@h/x")

    def test_url_y_ruta_segura(self):
        e = entorno_para_alembic({}, "postgresql://u:p@h/x_test")
        assert e["DATABASE_URL"] == "postgresql+asyncpg://u:p@h/x_test"
        assert e["PYTHONSAFEPATH"] == "1"

    def test_no_modifica_el_entorno_recibido(self):
        base = {"PYTHONPATH": str(RAIZ)}
        entorno_para_alembic(base, "postgresql://u:p@h/x")
        assert base == {"PYTHONPATH": str(RAIZ)}

    def test_alembic_arranca_aunque_la_raiz_este_en_pythonpath(self, monkeypatch):
        """Sin BD: `--help` basta para ver si el subproceso encuentra el alembic INSTALADO."""
        monkeypatch.setenv("PYTHONPATH", os.pathsep.join([SRC, str(RAIZ)]))
        r = alembic("postgresql://u:p@127.0.0.1:1/x_test", "--help", estricto=False)
        assert r.returncode == 0, r.stderr[-500:]

    def test_el_mecanismo_original_no_estaba_cubierto_por_pythonsafepath(self, monkeypatch):
        """Documenta la causa: con la raíz en PYTHONPATH, `PYTHONSAFEPATH=1` solo NO evita el choque."""
        entorno = dict(os.environ, PYTHONSAFEPATH="1",
                       PYTHONPATH=os.pathsep.join([SRC, str(RAIZ)]))
        r = subprocess.run([sys.executable, "-m", "alembic", "--help"], cwd=RAIZ, env=entorno,
                           capture_output=True, text=True, timeout=60)
        assert r.returncode != 0 and "alembic.__main__" in r.stderr


class TestGuardas:

    def test_se_niega_con_una_bd_sin_test_en_el_nombre(self):
        with pytest.raises(RuntimeError, match="no lleva 'test'"):
            exigir_nombre_de_prueba("postgresql://u:p@h/zascarr")

    def test_acepta_una_de_pruebas(self):
        assert exigir_nombre_de_prueba("postgresql://u:p@h/zascarr_test") == "zascarr_test"

    def test_migrar_no_toca_una_bd_que_no_parece_de_pruebas(self):
        with pytest.raises(RuntimeError, match="no lleva 'test'"):
            migrar_a_head("postgresql://u:p@127.0.0.1:1/produccion")

    @pytest.mark.asyncio
    async def test_la_efimera_tampoco_parte_de_una_bd_que_no_parece_de_pruebas(self):
        with pytest.raises(RuntimeError, match="no lleva 'test'"):
            async with bd_efimera("postgresql://u:p@127.0.0.1:1/produccion"):
                pass


@necesita_pg
class TestConPostgres:

    @pytest.mark.asyncio
    async def test_la_bd_compartida_llega_migrada_a_head(self):
        from zascarr.api.health import _alembic_head

        motor = create_async_engine(url_asyncpg(URL))
        try:
            async with motor.connect() as c:
                version = (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar()
        finally:
            await motor.dispose()
        assert version == _alembic_head()

    @pytest.mark.asyncio
    async def test_la_efimera_nace_vacia_se_puede_migrar_y_se_borra(self):
        from zascarr.api.health import _alembic_head

        async with bd_efimera(URL) as url:
            motor = create_async_engine(url_asyncpg(url))
            try:
                async with motor.connect() as c:
                    tablas = (await c.execute(text(
                        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
                    ))).scalar()
                assert tablas == 0                       # sin migrar: lo que exige el arranque degradado
                migrar_a_head(url)
                async with motor.connect() as c:
                    version = (await c.execute(text("SELECT version_num FROM alembic_version"))).scalar()
                assert version == _alembic_head()
            finally:
                await motor.dispose()
            nombre = url.rsplit("/", 1)[1]
        admin = create_async_engine(url_asyncpg(URL))
        try:
            async with admin.connect() as c:
                quedan = (await c.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname = :n"), {"n": nombre})).scalar()
        finally:
            await admin.dispose()
        assert quedan == 0

    @pytest.mark.asyncio
    async def test_la_efimera_se_borra_aunque_la_prueba_falle(self):
        nombre = None
        with pytest.raises(ZeroDivisionError):
            async with bd_efimera(URL) as url:
                nombre = url.rsplit("/", 1)[1]
                raise ZeroDivisionError
        admin = create_async_engine(url_asyncpg(URL))
        try:
            async with admin.connect() as c:
                quedan = (await c.execute(
                    text("SELECT count(*) FROM pg_database WHERE datname = :n"), {"n": nombre})).scalar()
        finally:
            await admin.dispose()
        assert quedan == 0
