# ruff: noqa: E501
"""#129 C sobre PostgreSQL real: retirar, historial, repetición y asociación cambiada."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_desvinculacion_pg import serie_de_prueba
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import MetadataSource, Series, VinculacionOperacion
from zascarr.services.retirar_asociacion import (
    RetirarAsociacionDeFuente,
    huella_de_asociacion_actual,
)
from zascarr.services.tokens_revision import (
    RetirarAsociacionFirmada,
    crear_token_retirar_asociacion,
)

SECRETO = "clave-de-prueba-para-retirar"
URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


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


def _entrada(operacion=None):
    return {"version": 1, "fuente": "gcd", "id_externo": "123", "entidad": "serie",
            "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
            "operacion_id": operacion or str(uuid4()), "origen": "confirmada",
            "modo": "busqueda"}


def _token(serie: Series, *, op=None):
    firmada = RetirarAsociacionFirmada(
        version=1, entidad="serie", fuente="gcd", id_externo="123",
        huella=huella_de_asociacion_actual(serie, "gcd"),
        operacion=op or str(uuid4()), serie_id=str(serie.id))
    return crear_token_retirar_asociacion(firmada, SECRETO)


@pytest.mark.asyncio
async def test_retirar_deja_columna_null_historial_y_comprobante_pg(entorno_base):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1, gcd_id=123)
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        serie.metadata_ = {"asociaciones": [_entrada()]}
        await s.commit()
        op = str(uuid4())
        token = _token(serie, op=op)
        r = await RetirarAsociacionDeFuente(s, secret=SECRETO).confirmar(token)
        assert r.resultado == "retirada" and r.repetida is False
        r2 = await RetirarAsociacionDeFuente(s, secret=SECRETO).confirmar(token)
        assert r2.resultado == "ya_retirada" and r2.repetida is True

    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        assert serie.gcd_id is None
        assert serie.metadata_["asociaciones"] == []
        hist = serie.metadata_["asociaciones_historial"]
        assert len(hist) == 1
        assert hist[0]["deshecho"]["operacion_id"] == op
        assert hist[0]["previo"]["fuente"] == "gcd"
        comprobantes = (await s.execute(select(VinculacionOperacion).where(
            VinculacionOperacion.operacion_id == op))).scalars().all()
        assert len(comprobantes) == 1
        assert comprobantes[0].resultado["tipo"] == "retirar_asociacion"


@pytest.mark.asyncio
async def test_asociacion_cambiada_entre_preview_y_confirmar_pg(entorno_base):
    sid = await serie_de_prueba(entorno_base, comic_vine_id=1, gcd_id=123)
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        serie.metadata_ = {"asociaciones": [_entrada()]}
        await s.commit()
        previa = await RetirarAsociacionDeFuente(s, secret=SECRETO).previsualizar(
            sid, MetadataSource.GCD)
        assert previa.token
        serie.gcd_id = 456
        await s.commit()
        r = await RetirarAsociacionDeFuente(s, secret=SECRETO).confirmar(previa.token)
        assert r.resultado == "omitida" and r.motivo == "propuesta_desactualizada"
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        assert serie.gcd_id == 456
