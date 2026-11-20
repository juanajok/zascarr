# ruff: noqa: F811
"""#1081: orden por última lectura real (MAX(last_read_at)), NULL al final."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import entorno  # noqa: F401
from zascarr.models import File, FileFormat, Issue, ReadingProgress, ReadingStatus, Series
from zascarr.services.series import SeriesService

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"),
                                reason="requiere TEST_DATABASE_URL")


async def _serie(s, titulo):
    sid = uuid4()
    s.add(Series(id=sid, title=titulo))
    iid = uuid4()
    s.add(Issue(id=iid, series_id=sid, issue_number="1", volume=1))
    s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{iid}.cbz",
               file_name="1.cbz", file_format=FileFormat.CBZ, metadata_={},
               is_missing=False))
    await s.flush()
    return sid, iid


@pytest.mark.asyncio
async def test_orden_por_ultima_lectura_y_nulls_al_final(entorno):
    async with entorno.banco.fabrica() as s:
        _, i_a = await _serie(s, "Antigua")
        _, i_b = await _serie(s, "Reciente")
        await _serie(s, "Sin lectura")
        s.add_all([
            ReadingProgress(id=uuid4(), issue_id=i_a, status=ReadingStatus.COMPLETED,
                            last_read_at=datetime(2024, 1, 1, tzinfo=UTC)),
            ReadingProgress(id=uuid4(), issue_id=i_b, status=ReadingStatus.READING,
                            last_read_at=datetime(2025, 1, 1, tzinfo=UTC)),
        ])
        await s.commit()
    async with entorno.banco.fabrica() as s:
        items, total, _ = await SeriesService(s).list_series_paginado(
            orden="leido_ultimo", page_size=10)
        antes = len(s.sentencias) if hasattr(s, "sentencias") else None
    assert total == 3
    assert [x.title for x in items] == ["Reciente", "Antigua", "Sin lectura"]
    assert antes is None or antes <= 2
