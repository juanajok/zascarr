# ruff: noqa: E501
"""#1187: el borrado no deja vínculos ni match_status colgados (Postgres real)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import File, FileFormat, Series
from zascarr.services.borrado_serie import BorradoDeSerie

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


@pytest.mark.asyncio
async def test_borrado_heredado_no_deja_vinculo_ni_match_status_colgados(entorno_base):
    sid, fid = uuid4(), uuid4()
    async with entorno_base.banco.fabrica() as s:
        s.add(Series(id=sid, title="Serie a borrar"))
        s.add(File(
            id=fid, file_path="/biblioteca/suelto.cbz", file_name="suelto.cbz",
            file_format=FileFormat.CBZ, issue_id=None, review_dismissed=False,
            metadata_={
                "vinculo": {"serie_id": str(sid), "operacion_id": "op1", "numero": "1"},
                "match_status": "matched",
            },
        ))
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        await BorradoDeSerie(s).borrar(sid)
    async with entorno_base.banco.fabrica() as s:
        assert (await s.execute(select(Series).where(Series.id == sid))).scalar_one_or_none() is None
        f = (await s.execute(select(File).where(File.id == fid))).scalar_one()
        meta = f.metadata_
        assert "vinculo" not in meta
        assert meta["match_status"] == "unsorted"
        assert meta["match_status_previo"] == "matched"
        assert meta["vinculo_historial"][-1]["deshecho"]["motivo"] == "serie_borrada"
