# ruff: noqa: E501
"""#129 B sobre PostgreSQL real: confirma, escribe columna+JSONB+comprobante y repite sin duplicar."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select

from tests.test_desvinculacion_pg import serie_de_prueba
from zascarr.models import Series, VinculacionOperacion
from zascarr.services.asociacion_fuente import AsociacionDeFuente
from zascarr.services.asociar_fuente import CandidataComparada, huella_de_asociacion
from zascarr.services.tokens_revision import AsociacionFirmada, crear_token_asociacion

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="requiere TEST_DATABASE_URL (Postgres real)")

SECRETO = "clave-de-prueba-para-asociar"


@pytest.fixture
async def entorno(entorno_base, monkeypatch):
    import zascarr.services.asociacion_fuente as modulo
    monkeypatch.setattr(modulo, "get_settings", lambda: SimpleNamespace(
        gcd_enabled=True, comicvine_enabled=True, anilist_enabled=True,
        tebeosfera_enabled=True))
    return entorno_base


def _firmada(serie: Series, *, op: str) -> tuple[str, CandidataComparada]:
    cand = CandidataComparada(
        titulo=serie.title, anio=serie.start_year, editorial=None, pais=None, idioma=None,
        id_externo="123", sitio_url="https://www.comics.org/series/123/",
        tradicion=None, kind="collection", fuente="gcd")
    firmada = AsociacionFirmada(
        version=1, entidad="serie", kind="collection", fuente="gcd", id_externo="123",
        titulo=cand.titulo, anio=cand.anio, sitio_url=cand.sitio_url,
        huella=huella_de_asociacion(serie, cand),
        operacion=op, serie_id=str(serie.id))
    return crear_token_asociacion(firmada, SECRETO), cand


@pytest.mark.asyncio
async def test_confirma_y_repeticion_no_duplica_pg(entorno):
    sid = await serie_de_prueba(entorno, comic_vine_id=1)
    op = str(uuid4())
    async with entorno.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        token, _ = _firmada(serie, op=op)
        r1 = await AsociacionDeFuente(s, secret=SECRETO).confirmar(token)
        assert r1.resultado == "asociada" and r1.repetida is False
        r2 = await AsociacionDeFuente(s, secret=SECRETO).confirmar(token)
        assert r2.resultado == "asociada" and r2.repetida is True

    async with entorno.banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        assert serie.gcd_id == 123
        activas = [e for e in serie.metadata_["asociaciones"] if e.get("fuente") == "gcd"]
        assert len(activas) == 1 and activas[0]["operacion_id"] == op
        assert activas[0]["origen"] == "confirmada"
        comprobantes = (await s.execute(select(VinculacionOperacion).where(
            VinculacionOperacion.operacion_id == op))).scalars().all()
        assert len(comprobantes) == 1
        assert comprobantes[0].resultado["tipo"] == "asociar_fuente"
