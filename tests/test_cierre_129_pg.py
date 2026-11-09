# ruff: noqa: E501
"""#129 cierre sobre PostgreSQL real: purgas H5, evidencia H3 y carrera H9."""
from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_asociar_fuente_b import _token as token_b
from tests.test_desvinculacion_pg import serie_de_prueba
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import Series, VinculacionOperacion
from zascarr.services.asociacion_fuente import AsociacionDeFuente
from zascarr.services.retirar_asociacion import (
    RetirarAsociacionDeFuente,
    huella_de_asociacion_actual,
)
from zascarr.services.tokens_revision import (
    RetirarAsociacionFirmada,
    crear_token_retirar_asociacion,
)

SECRETO = "x" * 32
URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def entorno(url_bd):
    import zascarr.services.asociacion_fuente as modulo
    modulo.get_settings = lambda: SimpleNamespace(
        gcd_enabled=True, comicvine_enabled=True, anilist_enabled=True,
        tebeosfera_enabled=True)
    banco = Banco(url_bd)
    await banco.limpiar()
    yield SimpleNamespace(banco=banco)
    await banco.cerrar()


def _entrada(op=None):
    return {"version": 1, "fuente": "gcd", "id_externo": "123", "entidad": "serie",
            "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
            "operacion_id": op or str(uuid4()), "origen": "confirmada", "modo": "busqueda"}


def _token_c(serie):
    return crear_token_retirar_asociacion(RetirarAsociacionFirmada(
        version=1, entidad="serie", fuente="gcd", id_externo="123",
        huella=huella_de_asociacion_actual(serie, "gcd"),
        operacion=str(uuid4()), serie_id=str(serie.id)), SECRETO)


async def _insertar_viejo(entorno, tipo, sid):
    op = uuid4()
    async with entorno.banco.fabrica() as s:
        await s.execute(text(
            "INSERT INTO vinculacion_operaciones (operacion_id, series_id, resultado, token_hasta, creada) "
            "VALUES (:o, :s, CAST(:r AS jsonb), now() - interval '2 hours', now() - interval '25 hours')"),
            {"o": op, "s": sid, "r": f'{{"tipo":"{tipo}"}}'})
        await s.commit()
    return op


@pytest.mark.asyncio
async def test_purga_asociar_fuente_borra_comprobante_viejo_pg(entorno):
    sid = await serie_de_prueba(entorno, comic_vine_id=1)
    viejo = await _insertar_viejo(entorno, "asociar_fuente", sid)
    async with entorno.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        token = token_b(serie)
        r = await AsociacionDeFuente(s, secret=SECRETO).confirmar(token)
        assert r.resultado == "asociada"
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(VinculacionOperacion).where(
            VinculacionOperacion.operacion_id == viejo))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_purga_retirar_asociacion_borra_comprobante_viejo_pg(entorno):
    sid = await serie_de_prueba(entorno, comic_vine_id=1, gcd_id=123)
    async with entorno.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        serie.metadata_ = {"asociaciones": [_entrada()]}
        await s.commit()
        token = _token_c(serie)
    viejo = await _insertar_viejo(entorno, "retirar_asociacion", sid)
    async with entorno.banco.fabrica() as s:
        r = await RetirarAsociacionDeFuente(s, secret=SECRETO).confirmar(token)
        assert r.resultado == "retirada"
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(VinculacionOperacion).where(
            VinculacionOperacion.operacion_id == viejo))).scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_dos_confirmaciones_concurrentes_no_duplican_pg(entorno):
    sid = await serie_de_prueba(entorno, comic_vine_id=1)
    async with entorno.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        t1 = token_b(serie, op=str(uuid4()))
        t2 = token_b(serie, op=str(uuid4()))

    async def confirmar(token):
        async with entorno.banco.fabrica() as s:
            return await AsociacionDeFuente(s, secret=SECRETO).confirmar(token)

    r1, r2 = await asyncio.gather(confirmar(t1), confirmar(t2))
    resultados = [r1.resultado, r2.resultado]
    assert resultados.count("asociada") == 1
    assert [r for r in resultados if r != "asociada"][0] in {"ya_asociada", "omitida"}
    async with entorno.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        assert serie.gcd_id == 123
        activas = [e for e in serie.metadata_["asociaciones"] if e.get("fuente") == "gcd"]
        assert len(activas) == 1
        n = (await s.execute(text("SELECT count(*) FROM vinculacion_operaciones WHERE series_id = :s"),
                             {"s": sid})).scalar_one()
        assert n == 1
