# ruff: noqa: E501
"""Corte D (#156): administrar raíces y mapa tradición→raíz con Postgres real."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.config import get_settings
from zascarr.models import File, FileFormat, LibraryRoot, LibraryRootTradition
from zascarr.services import raices

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def _entorno(monkeypatch, tmp_path):
    a = tmp_path / "library"
    b = tmp_path / "library2"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("LIBRARY_PATH", str(a))
    monkeypatch.setenv("LIBRARY_ROOTS", f"{a},{b}")
    monkeypatch.setenv("HOST_LIBRARY_ROOTS", "/host/a,/host/b")
    get_settings.cache_clear()
    return a, b


@pytest.mark.asyncio
async def test_crear_mapear_y_desactivar_sin_mover_archivos(monkeypatch, tmp_path):
    a, b = await _entorno(monkeypatch, tmp_path)
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                inicial = await raices.listar_con_tradiciones(s)
                assert len(inicial) == 1 and inicial[0].path == str(a)
                nueva = await raices.crear_raiz(s, path=str(b), name="Manga")
                await s.commit()
                assert nueva.id is not None
                await raices.guardar_mapa(s, {"manga": str(nueva.id)})
                await s.commit()
                mapa = {str(t.tradition.value): str(t.root_id)
                        for t in (await s.execute(select(LibraryRootTradition))).scalars().all()}
                assert mapa["manga"] == str(nueva.id)
                # El mapeo no toca rutas ni filas existentes.
                f = File(id=uuid4(), file_path=str(a / "x.cbz"), file_name="x.cbz",
                         file_format=FileFormat.CBZ)
                s.add(f)
                await s.commit()
                await raices.cambiar_habilitada(s, nueva.id, False)
                await s.commit()
                assert (await s.get(LibraryRoot, nueva.id)).enabled is False
                assert f.file_path == str(a / "x.cbz") and f.root_id is None
                assert len(await raices.listar_con_tradiciones(s)) == 2
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_la_raiz_por_defecto_se_cambia_sin_dejar_dos(monkeypatch, tmp_path):
    a, b = await _entorno(monkeypatch, tmp_path)
    async with bd_efimera(URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                nueva = await raices.crear_raiz(s, path=str(b), name="Manga")
                await s.commit()
                await raices.cambiar_por_defecto(s, nueva.id)
                await s.commit()
                defectos = (await s.execute(
                    select(LibraryRoot).where(LibraryRoot.is_default.is_(True)))).scalars().all()
                assert len(defectos) == 1 and defectos[0].id == nueva.id
                with pytest.raises(raices.RaizInvalidaError):
                    await raices.cambiar_habilitada(s, nueva.id, False)
        finally:
            await motor.dispose()
