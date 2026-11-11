"""BL-R7 (#236): las cinco vistas como consultas reales (Postgres en BD efímera)."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import File, FileFormat, Issue, IssueFormat, Series
from zascarr.services import vistas_trabajo as v

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring",
)


def _file(nombre, *, issue=None, sha=None, metadata=None, missing=False, dismissed=False):
    return File(
        id=uuid4(), file_path=f"/lib/{nombre}", file_name=nombre,
        file_format=FileFormat.CBZ, issue_id=issue.id if issue else None,
        sha256_hash=sha, metadata_=metadata or {}, is_missing=missing,
        review_dismissed=dismissed)


@pytest.mark.asyncio
async def test_cuentas_y_listas_de_las_cinco_vistas():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                serie = Series(id=uuid4(), title="Superman")
                s.add(serie)
                await s.flush()
                issues = {}
                for n in ("1", "2", "3", "4", "5"):
                    issues[n] = Issue(id=uuid4(), series_id=serie.id, issue_number=n,
                                      volume=1, format=IssueFormat.SINGLE_ISSUE)
                s.add_all(issues.values())
                await s.flush()

                # Sin identificar: sin issue y con match unsorted (no importa la ruta).
                s.add(_file("suelto.cbz", metadata={"match_status": "unsorted"}))
                # Dudosa: fuzzy, ya vinculada.
                s.add(_file("dudosa.cbz", issue=issues["1"], sha="d" * 64,
                            metadata={"match_status": "fuzzy", "match_score": 0.61}))
                # Discrepancia pendiente.
                s.add(_file("discrepancia.cbz", issue=issues["2"], sha="e" * 64,
                            metadata={"discrepancias": [{"estado": "pendiente",
                                                         "clave": "abc"}]}))
                # No disponible.
                s.add(_file("ausente.cbz", issue=issues["3"], sha="f" * 64, missing=True))
                # Variantes: dos contenidos distintos en la misma publicación.
                s.add_all([
                    _file("variante-a.cbz", issue=issues["4"], sha="a" * 64),
                    _file("variante-b.cbz", issue=issues["4"], sha="b" * 64),
                ])
                # Copia exacta: dos archivos con el MISMO contenido en otra publicación.
                s.add_all([
                    _file("copia-a.cbz", issue=issues["5"], sha="c" * 64),
                    _file("copia-b.cbz", issue=issues["5"], sha="c" * 64),
                ])
                await s.commit()

                cuentas = await v.contar_vistas(s)
                assert cuentas == {
                    "sin-identificar": 1, "dudosas": 1, "discrepancias": 1,
                    "no-disponibles": 1, "variantes": 1,
                }
                sin = await v.listar_vista(s, "sin-identificar")
                assert sin.filas[0].titulo == "suelto.cbz"
                dudosas = await v.listar_vista(s, "dudosas")
                discrepancias = await v.listar_vista(s, "discrepancias")
                assert dudosas.filas[0].titulo == "dudosa.cbz"
                assert discrepancias.filas[0].titulo == "discrepancia.cbz"
                variantes = await v.listar_vista(s, "variantes")
                assert variantes.total == 1
                assert variantes.filas[0].titulo == "#4 · Superman"
                assert "2 contenidos distintos" in variantes.filas[0].detalle
                # La copia exacta no entra en variantes.
                assert not any("copia" in f.titulo for f in variantes.filas)
                # Las vistas no escriben.
                antes = (await s.execute(select(func.count()).select_from(File))).scalar_one()
                await v.contar_vistas(s)
                await v.listar_vista(s, "discrepancias")
                despues = (await s.execute(select(func.count()).select_from(File))).scalar_one()
                assert antes == despues
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_la_pagina_recorta_en_sql_y_no_materializa_todo():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                for i in range(51):
                    s.add(_file(f"suelto-{i:02d}.cbz", metadata={"match_status": "unsorted"}))
                await s.commit()
                pagina = await v.listar_vista(s, "sin-identificar", 1)
                assert pagina.total == 51 and len(pagina.filas) == v.POR_PAGINA
                assert pagina.paginas == 2 and pagina.hasta == v.POR_PAGINA
                segunda = await v.listar_vista(s, "sin-identificar", 2)
                assert len(segunda.filas) == 1 and segunda.desde == v.POR_PAGINA
        finally:
            await motor.dispose()
