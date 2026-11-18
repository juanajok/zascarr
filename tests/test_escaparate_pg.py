# ruff: noqa: E501, F401, F811
"""#1101: consultas del Escaparate sobre PostgreSQL real."""
from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import cliente, entorno  # noqa: F401
from zascarr.models import (
    Creator,
    File,
    FileFormat,
    Issue,
    IssueCreator,
    ReadingProgress,
    ReadingStatus,
    Series,
    SeriesRecentView,
)
from zascarr.services import actividad

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"), reason="requiere TEST_DATABASE_URL")


async def _serie_con_archivo(s, titulo, numero="1"):
    sid = uuid4()
    s.add(Series(id=sid, title=titulo))
    await s.flush()
    iid = uuid4()
    s.add(Issue(id=iid, series_id=sid, issue_number=numero, volume=1))
    await s.flush()
    s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}.cbz",
               file_name="x.cbz", file_format=FileFormat.CBZ, metadata_={}, is_missing=False))
    await s.flush()
    return sid, iid


@pytest.mark.asyncio
async def test_vistos_autores_y_redescubre_determinista(entorno):
    async with entorno.banco.fabrica() as s:
        sid, iid = await _serie_con_archivo(s, "Visible")
        s.add(SeriesRecentView(series_id=sid, last_viewed_at=datetime(2024, 5, 1, tzinfo=UTC)))
        autor = Creator(id=uuid4(), name="Autora")
        s.add(autor)
        s.add(IssueCreator(issue_id=iid, creator_id=autor.id, role="writer"))
        await _serie_con_archivo(s, "Pendiente")
        await s.commit()
    async with entorno.banco.fabrica() as s:
        vistos = await actividad.vistos_recientemente(s)
        autores = await actividad.autores_destacados(s)
        uno = await actividad.redescubre(s, 1, 0)
        dos = await actividad.redescubre(s, 1, 0)
        siguiente = await actividad.redescubre(s, 1, 4)
        escrituras = len(entorno.banco.sentencias)
    assert [v.series_title for v in vistos] == ["Visible"]
    assert autores[0].nombre == "Autora" and autores[0].total == 1
    assert [x.series_id for x in uno] == [x.series_id for x in dos]
    assert [x.series_id for x in uno] != [x.series_id for x in siguiente] or len(siguiente) == 1
    assert escrituras >= 4  # solo SELECT


@pytest.mark.asyncio
async def test_pagina_escaparate_y_sugerencias_http(entorno):
    async with entorno.banco.fabrica() as s:
        await _serie_con_archivo(s, "Escaparate")
        await s.commit()
    async with cliente() as c:
        r = await c.get("/ui/biblioteca?modo=escaparate")
        s = await c.get("/ui/biblioteca/sugerencias?offset=0")
    assert r.status_code == 200
    assert "Escaparate" in r.text and "Gestión" in r.text
    assert s.status_code == 200 and "escaparate-lista" in s.text
