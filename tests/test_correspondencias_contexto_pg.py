# ruff: noqa: E501
"""MIT-M7 131-a sobre PostgreSQL real: versionado, ciclo, alcance y seis estados."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import (
    ComicTradition,
    CorrespondenciaContexto,
    EstadoRegla,
    Issue,
    IssueFormat,
    OrigenRegla,
    Series,
    TipoDestino,
    TipoRegistro,
)
from zascarr.services.correspondencias_contexto import (
    CorrespondenciaRetiradaError,
    DestinoInvalidoError,
    EvidenciaIncompatibleError,
    RegistroContextual,
    activar,
    cambiar,
    crear,
    desactivar,
    evaluar,
    historial,
    retirar,
)
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


async def _destinos(entorno):
    sid, iid, iid2 = uuid4(), uuid4(), uuid4()
    async with entorno.banco.fabrica() as s:
        s.add(Series(id=sid, title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN))
        s.add(Series(id=iid2, title="Otra", tradition=ComicTradition.AMERICAN))
        s.add(Series(id=uuid4(), title="Destino", tradition=ComicTradition.AMERICAN))
        await s.flush()
        s.add(Issue(id=iid, series_id=sid, issue_number="1", format=IssueFormat.SINGLE_ISSUE))
        await s.commit()
    return sid, iid


@pytest.mark.asyncio
async def test_crear_cambiar_desactivar_activar_retirar_pg(entorno):
    sid, iid = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        decl = await declarar(s, "Comics/A", tipo_de_significado="publicacion")
        c1 = await crear(s, decl.id, destino_tipo="serie", destino_id=sid)
        assert c1.version == 1 and c1.declaracion_version_id == decl.id
        c2 = await cambiar(s, c1.correspondencia_id, destino_id=iid,
                           destino_tipo="publicacion", tipo_de_registro="archivo")
        assert c2.version == 2 and c2.supersedes_id == c1.id
        c3 = await desactivar(s, c1.correspondencia_id)
        assert c3.estado is EstadoRegla.DESACTIVADA and c3.version == 3
        c4 = await activar(s, c1.correspondencia_id)
        assert c4.estado is EstadoRegla.ACTIVA and c4.version == 4
        c5 = await retirar(s, c1.correspondencia_id)
        assert c5.estado is EstadoRegla.RETIRADA and c5.version == 5
        with pytest.raises(CorrespondenciaRetiradaError):
            await activar(s, c1.correspondencia_id)
        assert [x.version for x in await historial(s, c1.correspondencia_id)] == [1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_destino_inexistente_no_se_crea_pg(entorno):
    sid, _ = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        decl = await declarar(s, "Comics/A", tipo_de_significado="publicacion")
        with pytest.raises(DestinoInvalidoError):
            await crear(s, decl.id, destino_tipo="serie", destino_id=uuid4())


async def _decl_corr(entorno):
    sid, _ = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        decl = await declarar(s, "Comics/A", tipo_de_significado="publicacion")
        corr = await crear(s, decl.id, destino_tipo="serie", destino_id=sid)
    return sid, decl, corr


@pytest.mark.asyncio
async def test_propuesta_fuera_de_alcance_y_sin_efectos_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        assert r.estado == "propuesta_disponible"
        assert r.propuesta.destino_id == sid and r.version_de_regla == 1
        fuera = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A/B"))
        assert fuera.estado == "fuera_de_alcance"
        antes = (await s.execute(select(func.count(CorrespondenciaContexto.id)))).scalar_one()
        await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        despues = (await s.execute(select(func.count(CorrespondenciaContexto.id)))).scalar_one()
        assert antes == despues == 1


@pytest.mark.asyncio
async def test_conflicto_mismo_destino_pg(entorno):
    sid, _ = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        d1 = await declarar(s, "Comics", tipo_de_significado="publicacion", incluir_descendientes=True)
        d2 = await declarar(s, "Comics/A", tipo_de_significado="publicacion")
        await crear(s, d1.id, destino_tipo="serie", destino_id=sid)
        await crear(s, d2.id, destino_tipo="serie", destino_id=sid)
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        assert r.estado == "conflicto_de_correspondencias"
        assert len(r.reglas_involucradas) == 2
        assert r.propuesta is None and r.correspondencia_id is None
        assert r.version_de_regla is None and r.destino_tipo is None and r.destino_id is None
        assert "no se elige" in r.motivo


@pytest.mark.asyncio
async def test_destino_no_disponible_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        await s.execute(Series.__table__.delete().where(Series.id == sid))
        await s.commit()
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        assert r.estado == "destino_no_disponible" and r.destino_id == sid


@pytest.mark.asyncio
async def test_evidencia_incompatible_autor_pg(entorno):
    _, iid = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        decl = await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        c = CorrespondenciaContexto(
            id=uuid4(), correspondencia_id=uuid4(), version=1,
            declaracion_version_id=decl.id, contexto_raiz=decl.contexto_raiz,
            incluir_descendientes=False, destino_tipo=TipoDestino.SERIE,
            destino_id=iid, origen=OrigenRegla.LOCAL, estado=EstadoRegla.ACTIVA)
        s.add(c)
        await s.commit()
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/Autor"))
        assert r.estado == "evidencia_incompatible"


@pytest.mark.asyncio
async def test_regla_desactualizada_al_cambiar_declaracion_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        await cambiar_declaracion(s, decl.declaracion_id, tipo_de_significado="publicacion",
                                  incluir_descendientes=True)
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        assert r.estado == "regla_desactualizada"
        assert r.correspondencia_id == corr.correspondencia_id


@pytest.mark.asyncio
async def test_tipo_de_registro_no_aplica_y_referencia_exacta_pg(entorno):
    sid, _ = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        decl = await declarar(s, "Comics/Tipo", tipo_de_significado="publicacion")
        c = await crear(s, decl.id, destino_tipo="serie", destino_id=sid,
                        tipo_de_registro="serie")
        assert c.tipo_de_registro is TipoRegistro.SERIE
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/Tipo"))
        assert r.estado == "fuera_de_alcance"
        prop = await evaluar(s, RegistroContextual(tipo="serie", carpeta="Comics/Tipo"))
        assert prop.estado == "propuesta_disponible"


@pytest.mark.asyncio
async def test_propuesta_retenida_v1_queda_desactualizada_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        retenida = r.propuesta
        assert retenida is not None
        await cambiar(s, corr.correspondencia_id, destino_id=sid, destino_tipo="serie",
                      tipo_de_registro="archivo")
        stale = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"),
                              retenida=retenida)
        assert stale.estado == "regla_desactualizada"
        assert stale.correspondencia_id == corr.correspondencia_id
        assert stale.declaracion_id == decl.declaracion_id
        assert stale.version_declaracion == decl.version


@pytest.mark.asyncio
async def test_desactivar_y_retirar_correspondencia_da_desactualizada_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        await desactivar(s, corr.correspondencia_id)
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        assert r.estado == "regla_desactualizada"
        assert r.declaracion_id == decl.declaracion_id and r.version_declaracion == decl.version
        await activar(s, corr.correspondencia_id)
        await retirar(s, corr.correspondencia_id)
        r2 = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"))
        assert r2.estado == "regla_desactualizada"


@pytest.mark.asyncio
async def test_ciclo_de_regla_incompatible_pg(entorno):
    _, iid = await _destinos(entorno)
    async with entorno.banco.fabrica() as s:
        decl = await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        c = CorrespondenciaContexto(
            id=uuid4(), correspondencia_id=uuid4(), version=1,
            declaracion_version_id=decl.id, contexto_raiz=decl.contexto_raiz,
            incluir_descendientes=False, destino_tipo=TipoDestino.SERIE,
            destino_id=iid, origen=OrigenRegla.LOCAL, estado=EstadoRegla.ACTIVA)
        s.add(c)
        await s.commit()
        cid = c.correspondencia_id
    async with entorno.banco.fabrica() as s:
        d = await desactivar(s, cid)
        assert d.estado is EstadoRegla.DESACTIVADA
    async with entorno.banco.fabrica() as s:
        with pytest.raises(EvidenciaIncompatibleError):
            await activar(s, cid)
    async with entorno.banco.fabrica() as s:
        r = await retirar(s, cid)
        assert r.estado is EstadoRegla.RETIRADA


@pytest.mark.asyncio
async def test_cambiar_raiz_identidad_y_limpiar_tipo_registro_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        otra = await declarar(s, "Comics/Otra", tipo_de_significado="publicacion")
        with pytest.raises(EvidenciaIncompatibleError):
            await cambiar(s, corr.correspondencia_id, declaracion_version_id=otra.id,
                          destino_tipo="serie", destino_id=sid)
        c = await cambiar(s, corr.correspondencia_id, tipo_de_registro="serie")
        assert c.tipo_de_registro is TipoRegistro.SERIE
        c2 = await cambiar(s, corr.correspondencia_id, tipo_de_registro=None)
        assert c2.tipo_de_registro is None


@pytest.mark.asyncio
async def test_propuesta_retenida_tras_cambiar_declaracion_pg(entorno):
    sid, decl, corr = await _decl_corr(entorno)
    async with entorno.banco.fabrica() as s:
        propuesta = (await evaluar(s, RegistroContextual(
            tipo="archivo", carpeta="Comics/A"))).propuesta
        nueva = await cambiar_declaracion(s, decl.declaracion_id,
                                          incluir_descendientes=True)
        r = await evaluar(s, RegistroContextual(tipo="archivo", carpeta="Comics/A"),
                          retenida=propuesta)
        assert r.estado == "regla_desactualizada"
        assert r.declaracion_id == decl.declaracion_id
        assert r.version_declaracion == nueva.version
