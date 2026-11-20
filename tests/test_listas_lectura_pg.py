# ruff: noqa: E501, F401, F811
"""#1080: listas de lectura curadas sobre PostgreSQL real."""
from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests.test_asociar_fuente_b_pg import url_bd  # noqa: F401
from tests.test_vinculacion_previa_pg import cliente, entorno  # noqa: F401
from zascarr.models import (
    File,
    FileFormat,
    Issue,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
    ReadingStatus,
    Series,
)
from zascarr.services import listas_lectura as servicio

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"),
                                reason="requiere TEST_DATABASE_URL")


async def _numero(s, sid, numero, leido=False):
    iid = uuid4()
    s.add(Issue(id=iid, series_id=sid, issue_number=numero, volume=1))
    await s.flush()
    s.add(File(id=uuid4(), issue_id=iid, file_path=f"/tmp/{uuid4()}.cbz",
               file_name="x.cbz", file_format=FileFormat.CBZ, metadata_={}, is_missing=False))
    if leido:
        s.add(ReadingProgress(id=uuid4(), issue_id=iid, status=ReadingStatus.COMPLETED))
    await s.flush()
    return iid


@pytest.mark.asyncio
async def test_crud_orden_duplicados_y_progreso(entorno):
    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Lista"))
        await s.flush()
        a = await _numero(s, sid, "1", leido=True)
        b = await _numero(s, sid, "2")
        c = await _numero(s, sid, "3")
        lista = await servicio.crear(s, "  Verano  ", "  Lecturas  ")
        await s.commit()
        lid = lista.id
    async with entorno.banco.fabrica() as s:
        resumen = await servicio.listar(s)
        assert resumen[0].nombre == "Verano" and resumen[0].descripcion == "Lecturas"
        await servicio.anadir(s, lid, a)
        await servicio.anadir(s, lid, b)
        await servicio.anadir(s, lid, c)
        with pytest.raises(servicio.ListaInvalidaError):
            await servicio.anadir(s, lid, a)
        assert await servicio.mover(s, lid, b, "subir") is True
        await s.commit()
    async with entorno.banco.fabrica() as s:
        datos = await servicio.detalle(s, lid)
        assert [x.numero for x in datos["items"]] == ["2", "1", "3"]
        assert datos["total"] == 3 and datos["leidos"] == 1
        assert [x.position for x in datos["items"]] == [1, 2, 3]
    async with entorno.banco.fabrica() as s:
        await servicio.quitar(s, lid, b)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        datos = await servicio.detalle(s, lid)
        assert [x.numero for x in datos["items"]] == ["1", "3"]
        assert [x.position for x in datos["items"]] == [1, 2]
        await servicio.renombrar(s, lid, "Invierno", "")
        await s.commit()
    async with entorno.banco.fabrica() as s:
        assert (await servicio.detalle(s, lid))["lista"].name == "Invierno"


@pytest.mark.asyncio
async def test_borrar_no_toca_numeros_y_cascada(entorno):
    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Cascada"))
        await s.flush()
        iid = await _numero(s, sid, "1")
        lista = await servicio.crear(s, "Temporal")
        await s.commit()
        lid = lista.id
        await servicio.anadir(s, lid, iid)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        await servicio.borrar(s, lid)
        await s.commit()
        assert await s.get(Issue, iid) is not None
        assert (await s.execute(select(func.count()).select_from(ReadingListItem))).scalar_one() == 0


@pytest.mark.asyncio
async def test_http_index_detalle_y_mover(entorno):
    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="HTTP"))
        await s.flush()
        iid = await _numero(s, sid, "1")
        lista = await servicio.crear(s, "HTTP lista")
        await s.commit()
        lid = lista.id
    async with cliente() as c:
        r = await c.get("/ui/listas")
        assert r.status_code == 200 and "HTTP lista" in r.text
        d = await c.get(f"/ui/listas/{lid}")
        assert d.status_code == 200 and "HTTP lista" in d.text
        opciones = await c.get(f"/ui/listas/opciones/{sid}/{iid}")
        assert opciones.status_code == 200 and "Añadir a una lista" in opciones.text
        assert (await c.post("/ui/listas/anadir", data={"lista_id": str(lid),
                                                        "issue_id": str(iid)})).status_code == 303
        assert "HTTP lista" in (await c.get(f"/ui/listas/{lid}")).text


@pytest.mark.asyncio
async def test_consultas_acotadas(entorno):
    sid = uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Cuenta"))
        await s.flush()
        iid = await _numero(s, sid, "1")
        lista = await servicio.crear(s, "Cuenta")
        await s.commit()
        lid = lista.id
        await servicio.anadir(s, lid, iid)
        await s.commit()
    async with entorno.banco.fabrica() as s:
        antes = len(entorno.banco.sentencias)
        await servicio.listar(s)
        assert len(entorno.banco.sentencias) - antes == 1
        antes = len(entorno.banco.sentencias)
        await servicio.detalle(s, lid)
        assert len(entorno.banco.sentencias) - antes <= 2
