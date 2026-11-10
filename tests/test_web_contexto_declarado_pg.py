# ruff: noqa: E501
"""MIT-M7 130-b: integración real de las cuatro rutas con ids estables."""
from __future__ import annotations

import os
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import DeclaracionCarpeta, EstadoRegla
from zascarr.services.declaraciones_carpeta import declarar

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd):
    banco = Banco(url_bd)
    await banco.limpiar()
    yield SimpleNamespace(banco=banco)
    await banco.cerrar()


@pytest.fixture
async def cliente(entorno):
    async def _db():
        async with entorno.banco.fabrica() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    try:
        async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://localhost",
                headers={"Origin": "http://localhost"}) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


async def _decl(entorno):
    async with entorno.banco.fabrica() as s:
        return await declarar(s, "Comics/Carlos", tipo_de_significado="autor")


@pytest.mark.asyncio
async def test_cambiar_desactivar_reactivar_retirar_con_id_estable(cliente, entorno):
    d = await _decl(entorno)
    assert (await cliente.get(f"/ui/pendientes/carpetas/cambiar/{d.declaracion_id}")).status_code == 200
    r = await cliente.post(f"/ui/pendientes/carpetas/desactivar/{d.declaracion_id}",
                           follow_redirects=False)
    assert r.status_code == 303
    r = await cliente.post(f"/ui/pendientes/carpetas/reactivar/{d.declaracion_id}",
                           follow_redirects=False)
    assert r.status_code == 303
    assert (await cliente.get(f"/ui/pendientes/carpetas/retirar/{d.declaracion_id}")).status_code == 200
    r = await cliente.post(f"/ui/pendientes/carpetas/retirar/{d.declaracion_id}",
                           follow_redirects=False)
    assert r.status_code == 303
    async with entorno.banco.fabrica() as s:
        actual = (await s.execute(select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.vigente_hasta.is_(None)))).scalar_one()
        assert actual.estado is EstadoRegla.RETIRADA


@pytest.mark.asyncio
async def test_redeclarar_retirada_crea_identidad_nueva(cliente, entorno):
    d = await _decl(entorno)
    assert (await cliente.post(f"/ui/pendientes/carpetas/retirar/{d.declaracion_id}",
                               follow_redirects=False)).status_code == 303
    r = await cliente.post("/ui/pendientes/carpetas/declarar",
                           data={"clave": "Comics/Carlos", "tipo": "publicacion"},
                           follow_redirects=False)
    assert r.status_code == 303 and "guardada" in r.headers["location"]
    async with entorno.banco.fabrica() as s:
        ids = {f.declaracion_id for f in
               (await s.execute(select(DeclaracionCarpeta))).scalars().all()}
        assert len(ids) == 2
