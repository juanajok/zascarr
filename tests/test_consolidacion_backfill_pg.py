# ruff: noqa: E501
"""H1: backfill estricto de `field_provenance` desde registros de fuente (Postgres real).

Se salta sin `TEST_DATABASE_URL`; base efímera."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, EntitySourceRecord, FieldProvenance, Series
from zascarr.services.consolidacion.backfill import BackfillEstricto

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno_base(url_bd):
    banco = Banco(url_bd)
    await banco.limpiar()
    yield SimpleNamespace(banco=banco)
    await banco.cerrar()


async def _preparar(entorno_base):
    async with entorno_base.banco.fabrica() as s:
        serie = Series(
            id=uuid4(), title="Serie CCM", tradition=ComicTradition.AMERICAN,
            metadata_source="comic_vine", comic_vine_id=123,
            start_year=1990, total_issues=12, end_year=1999, description="Sinopsis",
            metadata_={"vinculos_rol": {"comic_vine": "edicion_propia"}},
        )
        s.add(serie)
        await s.flush()
        s.add(EntitySourceRecord(
            entity_type="series", entity_id=serie.id, source="comic_vine",
            external_id="123", source_url="https://example.invalid/volume/123",
            license="prueba", payload={"normalizado": {
                "edition_scope": {"start_year": 1990, "total_issues": 12, "end_year": 2000},
                "work_scope": {"description": "Sinopsis"},
            }},
        ))
        await s.commit()
        return serie.id


@pytest.mark.asyncio
async def test_preview_no_escribe_y_cuenta_coincidencias(entorno_base):
    await _preparar(entorno_base)
    async with entorno_base.banco.fabrica() as s:
        r = await BackfillEstricto(s).ejecutar(preview=True)
        assert (r.series, r.filas, r.sin_coincidencia) == (1, 3, 1)
        assert r.preview is True
    async with entorno_base.banco.fabrica() as s:
        n = (await s.execute(select(func.count()).select_from(FieldProvenance))).scalar_one()
        assert n == 0


@pytest.mark.asyncio
async def test_apply_solo_campos_que_coinciden(entorno_base):
    sid = await _preparar(entorno_base)
    async with entorno_base.banco.fabrica() as s:
        r = await BackfillEstricto(s).ejecutar(preview=False)
        await s.commit()
        assert (r.series, r.filas, r.sin_coincidencia) == (1, 3, 1)
    async with entorno_base.banco.fabrica() as s:
        filas = {p.field: p for p in (await s.execute(select(FieldProvenance))).scalars()}
        assert set(filas) == {"start_year", "total_issues", "description"}
        assert all(p.source == "comic_vine" for p in filas.values())
        assert filas["start_year"].value["confianza"] == "fuente"
        assert filas["start_year"].value["valor"] == 1990
        assert filas["description"].value["valor"] == "Sinopsis"
        assert "end_year" not in filas          # 1999 != 2000: no se inventa
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        assert (serie.start_year, serie.total_issues, serie.end_year) == (1990, 12, 1999)
