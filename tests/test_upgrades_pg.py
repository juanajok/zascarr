"""BL-D3 (#154): escaneo periódico, propuestas persistentes y perfil D2 (PG)."""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
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
                    assert (await escanear_mejoras(s)).creadas == 1
                    assert (await escanear_mejoras(s)).creadas == 0
                await s.refresh(issue)
                assert issue.upgrade_scanned_at is not None
                propuestas = (await s.execute(select(UpgradeProposal))).scalars().all()
                assert len(propuestas) == 1
                assert propuestas[0].status == "pendiente"
                assert propuestas[0].candidate_tier == 3
                pagina = await listar_mejoras(s)
                assert len(pagina.filas) == 1 and pagina.filas[0].candidate_label == "alta"
                assert await descartar_mejora(s, propuestas[0].id)
                await s.commit()
                assert (await listar_mejoras(s)).filas == []
                # P0: descartar y reescanear el mismo número no debe romper el lote.
                issue.upgrade_scanned_at = datetime.now(UTC) - timedelta(hours=25)
                await s.commit()
                with patch("zascarr.services.upgrades.get_settings",
                           return_value=_settings()), \
                     patch("zascarr.services.upgrades.buscar_mejoras",
                           AsyncMock(return_value=resultado)):
                    assert (await escanear_mejoras(s)).creadas == 0
                assert len((await s.execute(select(UpgradeProposal))).scalars().all()) == 1
        finally:
            await motor.dispose()


def test_perfiles_mapean_a_objetivo():
    assert perfil_y_objetivo(_settings("mejor"))[1] == 3
    assert perfil_y_objetivo(_settings("equilibrado"))[1] == 2
    assert perfil_y_objetivo(_settings("cualquiera"))[1] == 0


@pytest.mark.asyncio
async def test_un_fallo_de_red_no_marca_el_numero_como_escaneado():
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
                s.add(File(id=uuid4(), issue_id=issue.id, file_path="/l/b2.cbz",
                           file_name="b2.cbz", file_format=FileFormat.CBZ,
                           is_missing=False, source_tag="scan", width_px=1000))
                await s.commit()
                fallo = ResultadoMejoras(False, "Prowlarr caído", [], [],
                                         reintentable=True)
                with patch("zascarr.services.upgrades.get_settings",
                           return_value=_settings()), \
                     patch("zascarr.services.upgrades.buscar_mejoras",
                           AsyncMock(return_value=fallo)):
                    assert (await escanear_mejoras(s)).creadas == 0
                await s.refresh(issue)
                assert issue.upgrade_scanned_at is None
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_reclamar_propuesta_impide_doble_descarga():
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
                propuesta = UpgradeProposal(
                    id=uuid4(), issue_id=issue.id, current_tier=1,
                    candidate_title="Batman 001", candidate_indexer="idx",
                    candidate_url="magnet:?xt=1", candidate_size_bytes=1,
                    candidate_seeders=1, candidate_tier=3)
                s.add(propuesta)
                await s.commit()
                from zascarr.services.upgrades import marcar_descargada, reclamar_mejora
                assert await reclamar_mejora(s, propuesta.id) is not None
                assert await reclamar_mejora(s, propuesta.id) is None
                assert await marcar_descargada(s, propuesta.id)
                await s.commit()
                await s.refresh(propuesta)
                assert propuesta.status == "descargada"
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_conciliar_propuesta_cuando_importa_el_archivo():
    from zascarr.models import FileFormat
    from zascarr.services.upgrades import historial_mejoras, reconciliar_mejora_importada
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
                file_id = uuid4()
                s.add(File(id=file_id, issue_id=issue.id, file_path="/l/x.cbz",
                           file_name="x.cbz", file_format=FileFormat.CBZ,
                           is_missing=False))
                propuesta = UpgradeProposal(
                    id=uuid4(), issue_id=issue.id, current_tier=1,
                    candidate_title="Batman 001 (Digital)", candidate_indexer="idx",
                    candidate_url="magnet:?xt=1", candidate_size_bytes=1,
                    candidate_seeders=1, candidate_tier=3, status="descargada")
                s.add(propuesta)
                await s.commit()
                assert await reconciliar_mejora_importada(s, issue.id, file_id)
                await s.commit()
                await s.refresh(propuesta)
                assert propuesta.status == "importada" and propuesta.file_id == file_id
                historial = await historial_mejoras(s)
                assert historial and historial[0].estado_label == "Importada en tu biblioteca"
        finally:
            await motor.dispose()
