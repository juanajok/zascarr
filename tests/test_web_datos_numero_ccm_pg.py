"""#1003: «Completar datos» de un número contra Postgres real."""
from __future__ import annotations

import os
from uuid import UUID

import httpx
import pytest

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import EntitySourceRecord, Issue, Series

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    async def _get_db():
        async with b.fabrica() as s:
            yield s
    app.dependency_overrides[get_db] = _get_db
    yield b
    app.dependency_overrides.pop(get_db, None)
    await b.cerrar()


def cliente() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                             base_url="http://localhost",
                             headers={"Origin": "http://localhost"})


async def _numero(banco: Banco) -> tuple[UUID, UUID]:
    sid = await banco.serie("Patrulla-X", 1985)
    async with banco.fabrica() as db:
        serie = await db.get(Series, sid)
        serie.metadata_ = {"vinculos_rol": {"comic_vine": "edicion_propia"}}
        issue = Issue(series_id=sid, issue_number="1", comic_vine_id=4001)
        db.add(issue)
        await db.flush()
        iid = issue.id
        db.add(EntitySourceRecord(
            entity_type="issue", entity_id=iid, source="comic_vine",
            external_id="4001", license="CV",
            payload={"normalizado": {"edition_scope": {
                "release_date": "2020-01-01", "page_count": 32},
                "work_scope": {"synopsis": "Una historia."}}},
            payload_hash="hi1"))
        await db.commit()
    return sid, iid


@pytest.mark.asyncio
async def test_pantalla_numero_y_aplicar_huecos(banco):
    sid, iid = await _numero(banco)
    async with cliente() as c:
        r = await c.get(f"/ui/series/{sid}/numero/{iid}/datos")
    assert r.status_code == 200
    assert "Completar datos del número" in r.text
    assert "Comic Vine" in r.text
    async with cliente() as c:
        r = await c.post(f"/ui/series/{sid}/numero/{iid}/datos/aplicar")
        assert r.status_code == 303
    async with banco.fabrica() as db:
        issue = await db.get(Issue, iid)
        await db.refresh(issue)
        assert issue.page_count == 32 and issue.release_date is not None
        assert issue.synopsis == "Una historia."
        assert issue.metadata_["comicinfo_sync_pendiente"] is True
