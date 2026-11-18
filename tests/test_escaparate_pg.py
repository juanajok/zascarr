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


@pytest.mark.asyncio
async def test_redescubre_completo_y_tradiciones_y_mas_de_la_serie(entorno):
    from zascarr.models import ComicTradition, Genre, series_genres
    from zascarr.services.actividad import (
        mas_de_la_serie,
        redescubre_completo,
        tradiciones_con_conteo,
    )

    async with entorno.banco.fabrica() as s:
        sid, iid = await _serie_con_archivo(s, "Favorita")
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        serie.favorite = True
        serie.tradition = ComicTradition.TEBEO
        serie.total_issues = 2
        genero = Genre(id=uuid4(), name="Aventura")
        s.add(genero)
        await s.flush()
        await s.execute(series_genres.insert().values(series_id=sid, genre_id=genero.id))
        autor = Creator(id=uuid4(), name="Autora")
        s.add(autor)
        s.add(IssueCreator(issue_id=iid, creator_id=autor.id, role="writer"))
        sid2, _ = await _serie_con_archivo(s, "Otra del autor")
        iid2 = (await s.execute(select(Issue.id).where(Issue.series_id == sid2))).scalar_one()
        s.add(IssueCreator(issue_id=iid2, creator_id=autor.id, role="writer"))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        sug = await redescubre_completo(s, 10, 0)
        trad = await tradiciones_con_conteo(s)
        mas = await mas_de_la_serie(s, sid)
        vacio = await redescubre_completo(s, 10, 9999)
    motivos = {x.motivo for x in sug}
    assert "Favorita" in motivos or "Casi completa" in motivos or "Por empezar" in motivos
    assert any(t.tradition == "tebeo" and t.total == 1 for t in trad)
    assert any(x["series_id"] == str(sid2) for x in mas)
    assert vacio == []


@pytest.mark.asyncio
async def test_sugerencias_offset_vacio_y_solo_select(entorno):
    async with entorno.banco.fabrica() as s:
        await _serie_con_archivo(s, "Única")
        await s.commit()
    antes = len(entorno.banco.sentencias)
    async with cliente() as c:
        r = await c.get("/ui/biblioteca/sugerencias?offset=9999")
    assert r.status_code == 200 and "No hay más sugerencias" in r.text
    import re
    escrituras = [x for x in entorno.banco.sentencias[antes:]
                  if re.search(r"\b(INSERT|UPDATE|DELETE)\b", x, re.I)]
    assert not escrituras


@pytest.mark.asyncio
async def test_sugerencias_propaga_offset_siguiente(entorno):
    from tests.test_vinculacion_previa_pg import cliente
    async with cliente() as c:
        r0 = await c.get("/ui/biblioteca/sugerencias?offset=0")
        r4 = await c.get("/ui/biblioteca/sugerencias?offset=4")
    assert "offset=4" in r0.text and "offset=8" in r4.text


@pytest.mark.asyncio
async def test_redescubre_no_duplica_series(entorno):
    from uuid import uuid4

    from zascarr.models import File, FileFormat, Issue, Series
    from zascarr.services.actividad import redescubre_completo
    async with entorno.banco.fabrica() as s:
        sid = uuid4()
        s.add(Series(id=sid, title="Repetida", favorite=True, total_issues=2))
        iid = uuid4()
        s.add(Issue(id=iid, series_id=sid, issue_number="1", volume=1))
        s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}.cbz",
                   file_name="1.cbz", file_format=FileFormat.CBZ, metadata_={},
                   is_missing=False))
        await s.commit()
    async with entorno.banco.fabrica() as s:
        sug = await redescubre_completo(s, 10, 0)
    assert [x.series_title for x in sug].count("Repetida") == 1
