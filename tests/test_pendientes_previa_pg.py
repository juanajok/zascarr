"""F1 (#636/#272): la vista previa de organizar no escribe (Postgres real)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import ComicTradition, File, FileFormat, Series
from zascarr.services.asignacion import previsualizar_asignacion

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring",
)


@pytest.mark.asyncio
async def test_previa_calcula_destino_y_no_escribe(tmp_path):
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            origen = tmp_path / "x.cbz"
            origen.write_bytes(b"contenido")
            async with fab() as s:
                serie = Series(id=uuid4(), title="Batman", start_year=2011,
                               tradition=ComicTradition.AMERICAN)
                f = File(id=uuid4(), file_path=str(origen), file_name="x.cbz",
                         file_format=FileFormat.CBZ)
                s.add_all([serie, f])
                await s.commit()
                previa = await previsualizar_asignacion(
                    s, tmp_path / "library", f.id, serie.id, "12")
                assert previa.estado == "ok"
                assert previa.serie == "Batman" and previa.numero == "12"
                assert previa.carpeta == "Batman (2011)"
                assert previa.nombre == "Batman #012.cbz"
                # No se ha creado operación ni se ha tocado el archivo.
                assert (await s.execute(
                    select(func.count()).select_from(File))).scalar_one() == 1
                from zascarr.models import AsignacionOperacion
                assert (await s.execute(
                    select(func.count()).select_from(AsignacionOperacion))).scalar_one() == 0
                assert origen.exists()
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_previa_con_numero_vacio_no_consulta_ni_escribe(tmp_path):
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                previa = await previsualizar_asignacion(
                    s, tmp_path / "library", uuid4(), uuid4(), "  ")
                assert previa.estado == "datos_no_validos"
                assert "Escribe el número" in previa.motivo
        finally:
            await motor.dispose()
