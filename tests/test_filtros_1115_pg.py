# ruff: noqa: F401, F811
"""#1115: filtros naturaleza/formato con EXISTS, sin duplicar series."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import entorno  # noqa: F401
from zascarr.models import File, FileFormat, Issue, IssueFormat, Series, SeriesKind
from zascarr.services.series import SeriesService

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"),
                                reason="requiere TEST_DATABASE_URL")


@pytest.mark.asyncio
async def test_formato_existe_sin_duplicar(entorno):
    sid, sid2 = uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add_all([Series(id=sid, title="Doble formato"), Series(id=sid2, title="Solo digital",
                                                                 kind=SeriesKind.ANNUAL)])
        i1, i2, i3 = uuid4(), uuid4(), uuid4()
        s.add_all([
            Issue(id=i1, series_id=sid, issue_number="1", volume=1,
                  format=IssueFormat.SINGLE_ISSUE),
            Issue(id=i2, series_id=sid, issue_number="2", volume=1,
                  format=IssueFormat.HARDCOVER),
            Issue(id=i3, series_id=sid2, issue_number="1", volume=1,
                  format=IssueFormat.DIGITAL),
        ])
        await s.flush()
        for n, iid, fmt in (("1.cbz", i1, FileFormat.CBZ), ("2.cbz", i2, FileFormat.CBZ),
                            ("3.cbz", i3, FileFormat.CBZ)):
            s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}-{n}",
                       file_name=n, file_format=fmt, metadata_={}, is_missing=False))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        items, total, _ = await SeriesService(s).list_series_paginado(
            format=IssueFormat.HARDCOVER.value, page_size=1)
        anual, total_anual, _ = await SeriesService(s).list_series_paginado(
            kind=SeriesKind.ANNUAL.value)
    assert total == 1 and [x.title for x in items] == ["Doble formato"]
    assert total_anual == 1 and anual[0].title == "Solo digital"


@pytest.mark.asyncio
async def test_edicion_y_formato_coexisten(entorno):
    from zascarr.models import EditionKind

    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Oficial tapa dura", edition_kind=EditionKind.OFICIAL))
        iid = uuid4()
        s.add(Issue(id=iid, series_id=sid, issue_number="1", volume=1,
                    format=IssueFormat.HARDCOVER))
        await s.flush()
        s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}.cbz",
                   file_name="1.cbz", file_format=FileFormat.CBZ, metadata_={},
                   is_missing=False))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        items, total, _ = await SeriesService(s).list_series_paginado(
            edition_kind=EditionKind.OFICIAL.value,
            format=IssueFormat.HARDCOVER.value)
    assert total == 1 and [x.title for x in items] == ["Oficial tapa dura"]
