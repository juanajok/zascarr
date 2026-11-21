# ruff: noqa: E501
"""B5a (#1185): retirar una asociación no puede dejar ids de número huérfanos.

Sobre PostgreSQL real y base efímera. Se salta sin `TEST_DATABASE_URL`."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_desvinculacion_pg import serie_de_prueba
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import Issue, Series
from zascarr.services.retirar_asociacion import (
    RetirarAsociacionDeFuente,
    huella_de_asociacion_actual,
)
from zascarr.services.tokens_revision import (
    RetirarAsociacionFirmada,
    crear_token_retirar_asociacion,
)

SECRETO = "clave-b5a-ids-huerfanos"
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


def _entrada_cv():
    return {"version": 1, "fuente": "comic_vine", "id_externo": "123", "entidad": "serie",
            "kind": "collection", "fecha": "2026-11-09T10:00:00+00:00",
            "operacion_id": str(uuid4()), "origen": "confirmada", "modo": "busqueda"}


def _token_cv(serie: Series):
    firmada = RetirarAsociacionFirmada(
        version=1, entidad="serie", fuente="comic_vine", id_externo="123",
        huella=huella_de_asociacion_actual(serie, "comic_vine"),
        operacion=str(uuid4()), serie_id=str(serie.id))
    return crear_token_retirar_asociacion(firmada, SECRETO)


async def _preparar(entorno_base) -> str:
    sid = await serie_de_prueba(entorno_base, comic_vine_id=123)
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        serie.metadata_ = {"asociaciones": [_entrada_cv()]}
        s.add_all([
            Issue(id=uuid4(), series_id=sid, issue_number="1", comic_vine_id=1001),
            Issue(id=uuid4(), series_id=sid, issue_number="2", comic_vine_id=1002),
        ])
        await s.commit()
    return sid


async def _retirar(entorno_base, sid: str):
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        return await RetirarAsociacionDeFuente(s, secret=SECRETO).confirmar(_token_cv(serie))


@pytest.mark.asyncio
async def test_retirar_asociacion_no_deja_ids_de_numero_huerfanos(entorno_base):
    sid = await _preparar(entorno_base)
    r = await _retirar(entorno_base, sid)
    assert r.resultado == "retirada"
    assert r.efectos["numeros"] == 2
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        issues = (await s.execute(select(Issue).where(Issue.series_id == sid))).scalars().all()
        assert serie.comic_vine_id is None
        assert all(i.comic_vine_id is None for i in issues)
        retirados = serie.metadata_["ids_numero_retirados"]
        assert len(retirados) == 1
        assert {x["id"] for x in retirados[0]["ids"]} == {1001, 1002}
        assert retirados[0]["fuente"] == "comic_vine"


@pytest.mark.asyncio
async def test_borrar_id_de_volumen_deja_historial_o_falla(entorno_base):
    sid = await _preparar(entorno_base)
    await _retirar(entorno_base, sid)
    async with entorno_base.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        assert serie.comic_vine_id is None
        hist = serie.metadata_["asociaciones_historial"]
        assert hist[-1]["deshecho"]["motivo"] == "retirada"
        assert hist[-1]["fuente"] == "comic_vine"
