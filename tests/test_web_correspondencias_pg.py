# ruff: noqa: E501
"""MIT-M7 131-b: TestClient con PostgreSQL real y ids reales."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import (
    ComicTradition,
    CorrespondenciaContexto,
    Issue,
    IssueFormat,
    Series,
)
from zascarr.services.correspondencias_contexto import crear
from zascarr.services.declaraciones_carpeta import cambiar as cambiar_declaracion
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


async def _base(entorno):
    async with entorno.banco.fabrica() as s:
        sid, iid = uuid4(), uuid4()
        s.add(Series(id=sid, title="Batman", tradition=ComicTradition.AMERICAN, start_year=2019))
        await s.flush()
        s.add(Issue(id=iid, series_id=sid, issue_number="1", title="El tribunal",
                    format=IssueFormat.SINGLE_ISSUE))
        decl = await declarar(s, "Comics/Batman", tipo_de_significado="publicacion")
        await s.commit()
    return sid, iid, decl


@pytest.mark.asyncio
async def test_crear_confirmar_y_ciclo_con_ids_reales(cliente, entorno):
    sid, _, decl = await _base(entorno)
    form = {"declaracion": str(decl.id), "tipo": "serie", "destino_id": str(sid),
            "tipo_registro": "archivo"}
    r = await cliente.post("/ui/pendientes/carpetas/correspondencias/crear", data=form)
    assert r.status_code == 200 and "Vas a crear una correspondencia" in r.text
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(CorrespondenciaContexto))).scalars().all() == []
    form["confirmado"] = "1"
    r = await cliente.post("/ui/pendientes/carpetas/correspondencias/crear", data=form,
                           follow_redirects=False)
    assert r.status_code == 303 and "aviso=creada" in r.headers["location"]
    async with entorno.banco.fabrica() as s:
        corr = (await s.execute(select(CorrespondenciaContexto))).scalar_one()
        cid = corr.correspondencia_id
    r = await cliente.get("/ui/pendientes/carpetas/correspondencias")
    assert "Activas (1)" in r.text and "Batman" in r.text
    assert (await cliente.get(f"/ui/pendientes/carpetas/correspondencias/cambiar/{cid}")).status_code == 200
    assert (await cliente.post(f"/ui/pendientes/carpetas/correspondencias/cambiar/{cid}",
                               data={"destino_tipo": "serie", "destino_id": str(sid),
                                     "tipo_registro": ""}, follow_redirects=False)).status_code == 303
    assert (await cliente.post(f"/ui/pendientes/carpetas/correspondencias/desactivar/{cid}",
                               follow_redirects=False)).status_code == 303
    assert (await cliente.post(f"/ui/pendientes/carpetas/correspondencias/reactivar/{cid}",
                               follow_redirects=False)).status_code == 303
    assert (await cliente.get(f"/ui/pendientes/carpetas/correspondencias/retirar/{cid}")).status_code == 200
    assert (await cliente.post(f"/ui/pendientes/carpetas/correspondencias/retirar/{cid}",
                               follow_redirects=False)).status_code == 303


@pytest.mark.asyncio
async def test_propuesta_disponible_y_fuera_alcance(cliente, entorno):
    sid, _, decl = await _base(entorno)
    async with entorno.banco.fabrica() as s:
        await crear(s, decl.id, destino_tipo="serie", destino_id=sid)
    r = await cliente.get("/ui/pendientes/carpetas/contexto/propuesta?clave=Comics%2FBatman")
    assert r.status_code == 200 and "Propuesta disponible" in r.text
    assert "Esto es una propuesta, no una decisión." in r.text
    r = await cliente.get("/ui/pendientes/carpetas/contexto/propuesta?clave=Comics%2FOtro")
    assert "Fuera de alcance" in r.text


@pytest.mark.asyncio
async def test_propuesta_conflicto_y_desactualizada(cliente, entorno):
    sid, _, decl = await _base(entorno)
    async with entorno.banco.fabrica() as s:
        d1 = await declarar(s, "Comics", tipo_de_significado="publicacion",
                            incluir_descendientes=True)
        await crear(s, d1.id, destino_tipo="serie", destino_id=sid)
        await crear(s, decl.id, destino_tipo="serie", destino_id=sid)
        await s.commit()
    r = await cliente.get("/ui/pendientes/carpetas/contexto/propuesta?clave=Comics%2FBatman")
    assert "Conflicto de correspondencias" in r.text
    assert "No se elige ninguna" in r.text


@pytest.mark.asyncio
async def test_propuesta_desactualizada(cliente, entorno):
    sid, _, decl = await _base(entorno)
    async with entorno.banco.fabrica() as s:
        await crear(s, decl.id, destino_tipo="serie", destino_id=sid)
        await cambiar_declaracion(s, decl.declaracion_id, incluir_descendientes=True)
    r = await cliente.get("/ui/pendientes/carpetas/contexto/propuesta?clave=Comics%2FBatman")
    assert "Desactualizada" in r.text
