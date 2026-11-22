# ruff: noqa: E501
"""#1189: locked_fields solo admite campos que existen (Postgres real)."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import Issue, Series
from zascarr.services.edicion_manual import desbloquear_numero, desbloquear_serie

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
async def test_locked_fields_solo_admite_campos_del_modelo(entorno_base):
    sid, iid = uuid4(), uuid4()
    async with entorno_base.banco.fabrica() as s:
        s.add(Series(id=sid, title="Serie", locked_fields=["genres", "publisher"]))
        s.add(Issue(id=iid, series_id=sid, issue_number="1", locked_fields=["credits"]))
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        assert await desbloquear_serie(s, sid, "genres") is True      # columna del modelo
        assert await desbloquear_serie(s, sid, "publisher") is True   # virtual de la edición
        assert await desbloquear_serie(s, sid, "no_existe") is False  # inventado: no
        assert await desbloquear_numero(s, sid, iid, "credits") is True
        assert await desbloquear_numero(s, sid, iid, "no_existe") is False
        await s.commit()
    async with entorno_base.banco.fabrica() as s:
        assert (await s.execute(select(Series.locked_fields).where(Series.id == sid))).scalar_one() == []
        assert (await s.execute(select(Issue.locked_fields).where(Issue.id == iid))).scalar_one() == []
