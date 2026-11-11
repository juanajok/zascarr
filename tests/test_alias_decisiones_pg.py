"""MIT-M7-US03 (#132-a): migración y ciclo de alias con Postgres real.

Comprueba que la migración 0026 conserva los alias existentes y los deja
`propuesto`, que el aprendizaje ya no activa, que el matcher solo usa alias
`activo` y que el alias importado versiona por filas.
"""
from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from tests._pg import alembic, bd_efimera, url_asyncpg
from zascarr.core.matcher import SeriesMatcher
from zascarr.models import AliasImportado, EstadoAlias, OrigenAlias, Series
from zascarr.services import alias_decisiones as svc

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — ver docstring",
)


def _sesion(url):
    motor = create_async_engine(url_asyncpg(url), poolclass=NullPool)
    return motor, async_sessionmaker(motor, expire_on_commit=False)


async def _series(sesion, titulo: str) -> UUID:
    serie = Series(id=uuid4(), title=titulo)
    sesion.add(serie)
    await sesion.flush()
    return serie.id


async def _limpiar(sesion, *series_ids):
    await sesion.execute(text("DELETE FROM alias_importado WHERE series_id = ANY(:ids)"),
                         {"ids": [str(s) for s in series_ids]})
    await sesion.execute(text("DELETE FROM local_aliases WHERE series_id = ANY(:ids)"),
                         {"ids": [str(s) for s in series_ids]})
    await sesion.execute(text("DELETE FROM series WHERE id = ANY(:ids)"),
                         {"ids": [str(s) for s in series_ids]})
    await sesion.commit()


@pytest.mark.asyncio
async def test_la_migracion_conserva_el_alias_y_lo_deja_propuesto():
    async with bd_efimera(TEST_DATABASE_URL) as url:
        alembic(url, "upgrade", "0025")
        motor, fabrica = _sesion(url)
        try:
            async with fabrica() as s:
                sid = uuid4()
                await s.execute(text(
                    "INSERT INTO series (id, title, tradition) "
                    "VALUES (:id, 'Superman', 'american')"), {"id": str(sid)})
                await s.execute(text(
                    "INSERT INTO local_aliases (id, pattern_norm, series_id) "
                    "VALUES (:id, 'superman godfall', :sid)"),
                    {"id": str(uuid4()), "sid": str(sid)})
                await s.commit()
        finally:
            await motor.dispose()

        alembic(url, "upgrade", "head")

        motor, fabrica = _sesion(url)
        try:
            async with fabrica() as s:
                fila = (await s.execute(text(
                    "SELECT estado, origen, version, historial FROM local_aliases "
                    "WHERE pattern_norm = 'superman godfall'"))).one()
                assert fila.estado == "propuesto"
                assert fila.origen == "aprendido"
                assert fila.version == 1
                assert fila.historial[0]["motivo"] == "migracion"
                # La tabla nueva existe y nace vacía.
                assert (await s.execute(text("SELECT count(*) FROM alias_importado"))).scalar() == 0
        finally:
            await motor.dispose()


@pytest.mark.asyncio
async def test_aprender_nace_propuesto_y_no_se_aplica_hasta_activar():
    motor, fabrica = _sesion(TEST_DATABASE_URL)
    try:
        async with fabrica() as s:
            sid = await _series(s, f"Superman {uuid4().hex[:6]}")
            patron = f"superman godfall {uuid4().hex[:6]}"
            alias = await svc.aprender_alias(s, patron, sid)
            await s.commit()
            assert alias.estado is EstadoAlias.PROPUESTO
            assert alias.version == 1 and alias.historial[-1]["motivo"] == "aprendizaje"

            matcher = SeriesMatcher(s)
            assert await matcher.find_alias(patron) is None      # propuesto NO se aplica

            await svc.activar_local(s, alias.id, confirmado=True)
            assert alias.estado is EstadoAlias.ACTIVO and alias.version == 2
            assert (await matcher.find_alias(patron)) is not None

            await svc.desactivar_local(s, alias.id)
            assert await matcher.find_alias(patron) is None       # desactivado NO se aplica

            await svc.reactivar_local(s, alias.id, confirmado=True)
            assert await matcher.find_alias(patron) is not None

            version_retirada = (await svc.retirar_local(s, alias.id)).version
            assert await matcher.find_alias(patron) is None
            assert (await svc.retirar_local(s, alias.id)).version == version_retirada  # idempotente
            with pytest.raises(svc.TransicionInvalidaError):
                await svc.reactivar_local(s, alias.id, confirmado=True)
            await _limpiar(s, sid)
    finally:
        await motor.dispose()


@pytest.mark.asyncio
async def test_activar_sin_confirmacion_no_cambia_nada():
    motor, fabrica = _sesion(TEST_DATABASE_URL)
    try:
        async with fabrica() as s:
            sid = await _series(s, f"Superman {uuid4().hex[:6]}")
            alias = await svc.aprender_alias(s, f"patron {uuid4().hex[:6]}", sid)
            await s.commit()
            with pytest.raises(svc.TransicionInvalidaError):
                await svc.activar_local(s, alias.id, confirmado=False)
            assert alias.estado is EstadoAlias.PROPUESTO and alias.version == 1
            await _limpiar(s, sid)
    finally:
        await motor.dispose()


@pytest.mark.asyncio
async def test_aprender_sobre_un_alias_activo_de_otra_serie_no_lo_pisa():
    motor, fabrica = _sesion(TEST_DATABASE_URL)
    try:
        async with fabrica() as s:
            sid_a = await _series(s, f"Superman {uuid4().hex[:6]}")
            sid_b = await _series(s, f"Superman Godfall {uuid4().hex[:6]}")
            patron = f"patron compartido {uuid4().hex[:6]}"
            alias = await svc.aprender_alias(s, patron, sid_a)
            await s.commit()
            await svc.activar_local(s, alias.id, confirmado=True)

            await svc.aprender_alias(s, patron, sid_b)
            await s.commit()

            assert alias.series_id == sid_a and alias.estado is EstadoAlias.ACTIVO
            assert alias.version == 2                     # solo la activación
            assert alias.historial[-1]["motivo"] == "conflicto"
            assert alias.historial[-1]["series_propuesta"] == str(sid_b)
            await _limpiar(s, sid_a, sid_b)
    finally:
        await motor.dispose()


@pytest.mark.asyncio
async def test_alias_importado_versiona_y_el_retiro_es_terminal():
    motor, fabrica = _sesion(TEST_DATABASE_URL)
    try:
        async with fabrica() as s:
            sid = await _series(s, f"Superman {uuid4().hex[:6]}")
            original = AliasImportado(
                id=uuid4(), alias_id=uuid4(), version=1, patron_norm=f"importado {uuid4().hex[:6]}",
                series_id=sid, origen=OrigenAlias.IMPORTADO, estado=EstadoAlias.PROPUESTO,
                procedencia={"fuente": "prueba"})
            s.add(original)
            await s.commit()

            activo = await svc.activar_importado(s, original.alias_id, confirmado=True)
            assert activo.version == 2 and activo.estado is EstadoAlias.ACTIVO
            assert activo.alias_id == original.alias_id
            cerrado = (await s.execute(
                text("SELECT vigente_hasta FROM alias_importado WHERE id = :id"),
                {"id": str(original.id)})).scalar()
            assert cerrado is not None

            desactivado = await svc.desactivar_importado(s, original.alias_id)
            assert desactivado.version == 3 and desactivado.estado is EstadoAlias.DESACTIVADO
            reactivado = await svc.reactivar_importado(s, original.alias_id, confirmado=True)
            assert reactivado.version == 4 and reactivado.estado is EstadoAlias.ACTIVO
            retirado = await svc.retirar_importado(s, original.alias_id)
            assert retirado.version == 5 and retirado.estado is EstadoAlias.RETIRADO
            assert (await svc.retirar_importado(s, original.alias_id)).id == retirado.id
            with pytest.raises(svc.TransicionInvalidaError):
                await svc.reactivar_importado(s, original.alias_id, confirmado=True)

            vigentes = await svc.listar_importados(s)
            assert len([a for a in vigentes if a.alias_id == original.alias_id]) == 1
            await _limpiar(s, sid)
    finally:
        await motor.dispose()
