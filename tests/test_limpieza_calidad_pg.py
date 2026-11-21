# ruff: noqa: E501
"""Lotes L2/L3/L4 del informe de calidad, sobre Postgres real.

Se salta sin `TEST_DATABASE_URL`; la base es efímera y migrada a `head`."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import bd_efimera_sync, migrar_a_head, url_asyncpg
from zascarr.models import Character, Creator, File, FileFormat, Issue, Series
from zascarr.services.limpieza_calidad import LimpiezaCalidad

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def fabrica(url_bd):
    engine = create_async_engine(url_asyncpg(url_bd), poolclass=NullPool)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def ids(fabrica):
    async with fabrica() as s:
        await s.execute(text("TRUNCATE files, issues, series, creators, characters RESTART IDENTITY CASCADE"))
        serie = Series(id=uuid4(), title="Serie con locks", locked_fields=["title", "no_existe"])
        limpia = Series(id=uuid4(), title="Serie limpia", locked_fields=["title"])
        s.add_all([serie, limpia])
        await s.flush()
        issue = Issue(id=uuid4(), series_id=serie.id, issue_number="1",
                      locked_fields=["synopsis", "mal"])
        creator = Creator(id=uuid4(), name="Creador X", locked_fields=["name", "bad"])
        character = Character(id=uuid4(), name="Personaje X", locked_fields=["name", "bad2"])
        s.add_all([issue, creator, character])
        await s.flush()
        stale = File(id=uuid4(), file_path="/biblioteca/stale.cbz", file_name="stale.cbz",
                     file_format=FileFormat.CBZ, issue_id=None, review_dismissed=False,
                     metadata_={"vinculo": {
                         "serie_id": str(uuid4()), "operacion_id": "op1", "numero": "1",
                         "previo": {"match_status": "matched", "metadata_source": "comicvine"}},
                         "match_status": "unsorted", "otra": "clave"})
        oculto = File(id=uuid4(), file_path="/biblioteca/oculto.cbz", file_name="oculto.cbz",
                      file_format=FileFormat.CBZ, issue_id=None, review_dismissed=False,
                      metadata_={"match_status": "matched", "otra": "x"})
        asignado = File(id=uuid4(), file_path="/biblioteca/asignado.cbz", file_name="asignado.cbz",
                        file_format=FileFormat.CBZ, issue_id=issue.id, review_dismissed=False,
                        metadata_={"match_status": "matched"})
        ignorado = File(id=uuid4(), file_path="/biblioteca/ignorado.cbz", file_name="ignorado.cbz",
                        file_format=FileFormat.CBZ, issue_id=None, review_dismissed=True,
                        metadata_={"match_status": "matched"})
        s.add_all([stale, oculto, asignado, ignorado])
        await s.commit()
        return {"serie": serie.id, "limpia": limpia.id, "issue": issue.id, "creator": creator.id,
                "character": character.id, "stale": stale.id, "oculto": oculto.id,
                "asignado": asignado.id, "ignorado": ignorado.id}


async def _previsualizar(fabrica, lote, **kw):
    async with fabrica() as s:
        return await LimpiezaCalidad(s).previsualizar(lote, **kw)


async def _aplicar(fabrica, lote, **kw):
    async with fabrica() as s:
        r = await LimpiezaCalidad(s).aplicar(lote, **kw)
        await s.commit()
        return r


async def _file(fabrica, fid):
    async with fabrica() as s:
        return (await s.execute(select(File).where(File.id == fid))).scalar_one()


async def _locks(fabrica, modelo, oid):
    async with fabrica() as s:
        return (await s.execute(select(modelo.locked_fields).where(modelo.id == oid))).scalar_one()


@pytest.mark.asyncio
async def test_vistas_previas_no_escriben(fabrica, ids):
    v3 = await _previsualizar(fabrica, "l3")
    assert v3.pendientes == 1 and len(v3.muestra) == 1
    v2 = await _previsualizar(fabrica, "l2")
    assert v2.pendientes == 1 and len(v2.muestra) == 1
    v4 = await _previsualizar(fabrica, "l4")
    assert v4.pendientes == 4 and len(v4.muestra) == 4
    # Sin escrituras: el oculto sigue como estaba y el vínculo sigue ahí.
    assert (await _file(fabrica, ids["oculto"])).metadata_["match_status"] == "matched"
    assert "vinculo" in (await _file(fabrica, ids["stale"])).metadata_
    assert "no_existe" in await _locks(fabrica, Series, ids["serie"])


@pytest.mark.asyncio
async def test_l3_devuelve_a_revisar(fabrica, ids):
    r = await _aplicar(fabrica, "l3")
    assert (r.pendientes_antes, r.cambiadas, r.pendientes_despues) == (1, 1, 0)
    meta = (await _file(fabrica, ids["oculto"])).metadata_
    assert meta["match_status"] == "unsorted"
    assert meta["match_status_previo"] == "matched"
    assert meta["otra"] == "x"
    # El asignado y el ignorado no se tocan.
    assert (await _file(fabrica, ids["asignado"])).metadata_["match_status"] == "matched"
    assert (await _file(fabrica, ids["ignorado"])).metadata_["match_status"] == "matched"


@pytest.mark.asyncio
async def test_l2_retira_vinculo_y_conserva_historial(fabrica, ids):
    r = await _aplicar(fabrica, "l2")
    assert (r.pendientes_antes, r.cambiadas, r.pendientes_despues) == (1, 1, 0)
    meta = (await _file(fabrica, ids["stale"])).metadata_
    assert "vinculo" not in meta
    assert meta["otra"] == "clave"
    entrada = meta["vinculo_historial"][-1]
    assert entrada["operacion_id"] == "op1"
    assert entrada["serie_id"]
    assert entrada["deshecho"]["motivo"] == "serie_borrada"
    assert entrada["deshecho"]["operacion_id"]


@pytest.mark.asyncio
async def test_l4_retira_nombres_invalidos(fabrica, ids):
    r = await _aplicar(fabrica, "l4")
    assert (r.pendientes_antes, r.cambiadas, r.pendientes_despues) == (4, 4, 0)
    assert await _locks(fabrica, Series, ids["serie"]) == ["title"]
    assert await _locks(fabrica, Series, ids["limpia"]) == ["title"]
    assert await _locks(fabrica, Issue, ids["issue"]) == ["synopsis"]
    assert await _locks(fabrica, Creator, ids["creator"]) == ["name"]
    assert await _locks(fabrica, Character, ids["character"]) == ["name"]


@pytest.mark.asyncio
async def test_idempotente(fabrica, ids):
    for lote in ("l3", "l2", "l4"):
        assert (await _aplicar(fabrica, lote)).cambiadas > 0
    for lote in ("l3", "l2", "l4"):
        r = await _aplicar(fabrica, lote)
        assert (r.pendientes_antes, r.cambiadas, r.pendientes_despues) == (0, 0, 0)
