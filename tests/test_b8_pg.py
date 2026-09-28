"""Regresión Postgres de B8 (fuentes on/off): filtro antes del LIMIT y contrato
de reactivación. Se salta sin TEST_DATABASE_URL, mismo patrón que
test_huecos_pg.py — requiere una base migrada (alembic upgrade head).

    docker run --rm -d --name zascarr_test_pg -e POSTGRES_PASSWORD=test \\
        -e POSTGRES_DB=zascarr -p 15433:5432 postgres:15-alpine
    DATABASE_URL=postgresql+asyncpg://postgres:test@localhost:15433/zascarr \\
        alembic upgrade head
    TEST_DATABASE_URL=postgresql://postgres:test@localhost:15433/zascarr \\
        pytest tests/test_b8_pg.py
"""
from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from zascarr.models import ComicTradition, Series
from zascarr.services.anilist import AniListResult
from zascarr.services.enricher import EnrichmentReport, EnrichmentService
from zascarr.services.tebeosfera import TebeosferaResult

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring del módulo",
)


def _url_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


async def _exigir_bd_de_prueba(session) -> None:
    nombre = (await session.execute(text("SELECT current_database()"))).scalar()
    if not nombre or "test" not in nombre.lower():
        raise RuntimeError(
            f"TEST_DATABASE_URL apunta a «{nombre}» (sin 'test'); se niega a ejecutarse."
        )


@pytest.fixture
async def db():
    engine = create_async_engine(_url_asyncpg(TEST_DATABASE_URL))
    sesion = async_sessionmaker(engine, expire_on_commit=False)
    async with sesion() as session:
        transaccion = await session.begin()
        await _exigir_bd_de_prueba(session)
        try:
            yield session
        finally:
            await transaccion.rollback()
    await engine.dispose()


def _serie(title: str, tradition: ComicTradition) -> Series:
    return Series(id=uuid4(), title=title, tradition=tradition)


class TestFuentesOnOffPg:

    @pytest.mark.asyncio
    async def test_fuente_desactivada_no_acapara_el_lote(self, db):
        """20 mangas (AniList apagada) + 1 tebeo (Tebeosfera activa): el filtro
        debe excluir las tradiciones desactivadas ANTES del LIMIT, o el tebeo
        se quedaría sin turno para siempre."""
        for i in range(20):
            db.add(_serie(f"Manga {i}", ComicTradition.MANGA))
        tebeo = _serie("Thorgal", ComicTradition.FRANCO_BELGIAN)
        db.add(tebeo)
        await db.flush()

        tebeosfera = AsyncMock()
        tebeosfera.search_series.return_value = [
            TebeosferaResult(slug="thorgal_1977", title="Thorgal", kind="saga", start_year=1977),
        ]
        report = EnrichmentReport()
        await EnrichmentService(db=db)._enrich_series_batch(
            None, None, tebeosfera, limit=20, report=report,
        )

        assert tebeo.tebeosfera_slug == "thorgal_1977"
        assert report.series_enriched == ["Thorgal"]

    @pytest.mark.asyncio
    async def test_reactivar_respeta_el_cooldown(self, db):
        """B8: reactivar NO resetea la caché negativa — un intento reciente
        sigue bajo el cooldown de 30 días; uno antiguo (o NULL) es elegible."""
        reciente = _serie("Berserk Reciente", ComicTradition.MANGA)
        reciente.enrichment_attempted_at = datetime.now(UTC)
        antigua = _serie("Berserk Antigua", ComicTradition.MANGA)
        antigua.enrichment_attempted_at = datetime.now(UTC) - timedelta(days=40)
        db.add(reciente)
        db.add(antigua)
        await db.flush()

        anilist = AsyncMock()
        anilist.search_manga.return_value = [
            AniListResult(anilist_id=42, title_romaji="Berserk Antigua", chapters=370),
        ]
        report = EnrichmentReport()
        await EnrichmentService(db=db)._enrich_series_batch(
            AsyncMock(), anilist, AsyncMock(), limit=10, report=report,
        )

        assert antigua.anilist_id == 42          # fuera de cooldown → elegible
        assert reciente.anilist_id is None       # aún en cooldown → no elegible
        assert report.series_enriched == ["Berserk Antigua"]
