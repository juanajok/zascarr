"""BL-D3 (#154): escaneo periódico, propuestas persistentes y perfil D2 (PG)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.models import File, FileFormat, Issue, Series, UpgradeProposal
from zascarr.services.calidad import (
    ArchivoActual,
    Calidad,
    MejoraCandidata,
    ResultadoMejoras,
)
from zascarr.services.prowlarr import SearchResult
from zascarr.services.upgrades import (
    descartar_mejora,
    escanear_mejoras,
    listar_mejoras,
    perfil_y_objetivo,
)

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


def _settings(perfil="equilibrado"):
    return SimpleNamespace(quality_profile=perfil, prowlarr_enabled=True,
                           prowlarr_url="http://prowlarr:9696",
                           prowlarr_api_key="clave", upgrade_scan_batch=3)


def _candidato():
    return MejoraCandidata(
        SearchResult("Batman 001 (Digital).cbz", "idx", "magnet:?xt=1",
                     20_000_000, 5, "comics"),
        Calidad(3, "alta", "digital"))


@pytest.mark.asyncio
async def test_escanear_crea_propuesta_y_no_repite():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "head")
        motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
        fab = async_sessionmaker(motor, expire_on_commit=False)
        try:
            async with fab() as s:
                serie = Series(id=uuid4(), title="Batman")
                s.add(serie)
                await s.flush()
                issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1", volume=1)
                s.add(issue)
                await s.flush()
                s.add(File(id=uuid4(), issue_id=issue.id, file_path="/l/b1.cbz",
                           file_name="b1.cbz", file_format=FileFormat.CBZ,
                           is_missing=False, source_tag="scan", width_px=1000))
                await s.commit()
                resultado = ResultadoMejoras(
                    True, None,
                    [ArchivoActual("b1.cbz", Calidad(1, "básica", "1000 px"))],
                    [_candidato()])
                with patch("zascarr.services.upgrades.get_settings",
                           return_value=_settings()), \
                     patch("zascarr.services.upgrades.buscar_mejoras",
                           AsyncMock(return_value=resultado)):
                    assert await escanear_mejoras(s) == 1
                    assert await escanear_mejoras(s) == 0
                await s.refresh(issue)
                assert issue.upgrade_scanned_at is not None
                propuestas = (await s.execute(select(UpgradeProposal))).scalars().all()
                assert len(propuestas) == 1
                assert propuestas[0].status == "pendiente"
                assert propuestas[0].candidate_tier == 3
                filas = await listar_mejoras(s)
                assert len(filas) == 1 and filas[0].candidate_label == "alta"
                assert await descartar_mejora(s, propuestas[0].id)
                await s.commit()
                assert await listar_mejoras(s) == []
        finally:
            await motor.dispose()


def test_perfiles_mapean_a_objetivo():
    assert perfil_y_objetivo(_settings("mejor"))[1] == 3
    assert perfil_y_objetivo(_settings("equilibrado"))[1] == 2
    assert perfil_y_objetivo(_settings("cualquiera"))[1] == 0
