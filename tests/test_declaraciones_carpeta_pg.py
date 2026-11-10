# ruff: noqa: E501
"""MIT-M7 #130-a sobre PostgreSQL real: versionado, unicidad, historial y ciclo."""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import DeclaracionCarpeta, EstadoRegla, OrigenRegla, TipoSignificadoCarpeta
from zascarr.services.declaraciones_carpeta import (
    DeclaracionDuplicadaError,
    DeclaracionRetiradaError,
    RutaInvalidaError,
    TipoInvalidoError,
    cambiar,
    declarar,
    desactivar,
    historial,
    listar,
    reactivar,
    retirar,
    vigente,
)

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


@pytest.mark.asyncio
async def test_declarar_crea_v1_y_normaliza_pg(entorno):
    async with entorno.banco.fabrica() as s:
        v = await declarar(s, "Cómics\\Autor//", tipo_de_significado="autor",
                           incluir_descendientes=False, procedencia={"operacion_id": "x"})
        assert v.version == 1 and v.contexto_raiz == "Cómics/Autor"
        assert v.estado is EstadoRegla.ACTIVA and v.origen is OrigenRegla.LOCAL
        assert v.procedencia == {"operacion_id": "x"}
        assert v.alcance == "Solo esta carpeta"
    async with entorno.banco.fabrica() as s:
        filas = (await s.execute(select(DeclaracionCarpeta))).scalars().all()
        assert len(filas) == 1 and filas[0].vigente_hasta is None


@pytest.mark.asyncio
async def test_una_activa_local_por_raiz_pg(entorno):
    async with entorno.banco.fabrica() as s:
        await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        with pytest.raises(DeclaracionDuplicadaError):
            await declarar(s, "Comics/Autor", tipo_de_significado="publicacion")
        # la importada sí puede coexistir con la local
        imp = await declarar(s, "Comics/Autor", tipo_de_significado="publicacion",
                             origen="importacion")
        assert imp.origen is OrigenRegla.IMPORTACION


@pytest.mark.asyncio
async def test_cambiar_dos_veces_cierra_versiones_y_conserva_historial_pg(entorno):
    async with entorno.banco.fabrica() as s:
        v1 = await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        v2 = await cambiar(s, v1.declaracion_id, tipo_de_significado="publicacion",
                           incluir_descendientes=True)
        v3 = await cambiar(s, v1.declaracion_id, incluir_descendientes=False)
        assert (v1.version, v2.version, v3.version) == (1, 2, 3)
        assert v3.estado is EstadoRegla.ACTIVA and v3.tipo_de_significado is TipoSignificadoCarpeta.PUBLICACION
        hist = await historial(s, v1.declaracion_id)
        assert [h.version for h in hist] == [1, 2, 3]
        assert hist[0].vigente_hasta is not None and hist[1].vigente_hasta is not None
        assert hist[2].vigente_hasta is None
        actual = await vigente(s, "Comics/Autor")
        assert actual is not None and actual.version == 3
    async with entorno.banco.fabrica() as s:
        current = (await s.execute(select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.vigente_hasta.is_(None)))).scalars().all()
        assert len(current) == 1 and current[0].version == 3


@pytest.mark.asyncio
async def test_desactivar_reactivar_y_retirar_pg(entorno):
    async with entorno.banco.fabrica() as s:
        v1 = await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        off = await desactivar(s, v1.declaracion_id)
        assert off.estado is EstadoRegla.DESACTIVADA and off.version == 2
        assert await vigente(s, "Comics/Autor") is None
        on = await reactivar(s, v1.declaracion_id)
        assert on.estado is EstadoRegla.ACTIVA and on.version == 3
        ret = await retirar(s, v1.declaracion_id)
        assert ret.estado is EstadoRegla.RETIRADA and ret.version == 4
        with pytest.raises(DeclaracionRetiradaError):
            await reactivar(s, v1.declaracion_id)
        assert len(await historial(s, v1.declaracion_id)) == 4
    async with entorno.banco.fabrica() as s:
        assert (await s.execute(select(DeclaracionCarpeta))).scalars().all()
        # el historial no se borra y ninguna versión queda vigente
        assert await vigente(s, "Comics/Autor") is None


@pytest.mark.asyncio
async def test_listar_filtra_y_no_afecta_a_otras_tablas_pg(entorno):
    async with entorno.banco.fabrica() as s:
        await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        pub = await declarar(s, "Comics/Publicacion", tipo_de_significado="publicacion")
        await desactivar(s, pub.declaracion_id)
        activas = await listar(s, tipo="autor")
        assert len(activas) == 1 and activas[0].contexto_raiz == "Comics/Autor"
        assert activas[0].efectos.startswith("Solo orienta")
        todas = await listar(s, incluir_historial=True)
        assert len(todas) == 3
        assert (await s.execute(text("SELECT count(*) FROM series"))).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM files"))).scalar_one() == 0


@pytest.mark.asyncio
async def test_rutas_y_tipos_invalidos_pg(entorno):
    async with entorno.banco.fabrica() as s:
        for ruta in ("", "/media/library", "../fuera", "a/../../b"):
            with pytest.raises(RutaInvalidaError):
                await declarar(s, ruta, tipo_de_significado="autor")
        with pytest.raises(RutaInvalidaError):
            await declarar(s, "Comics", tipo_de_significado="autor",
                           raiz_biblioteca="Comics")
        with pytest.raises(TipoInvalidoError):
            await declarar(s, "Comics/Otro", tipo_de_significado="otro")
        assert (await s.execute(select(DeclaracionCarpeta))).scalars().all() == []


@pytest.mark.asyncio
async def test_una_vigente_por_identidad_en_bd_pg(entorno):
    async with entorno.banco.fabrica() as s:
        v = await declarar(s, "Comics/Autor", tipo_de_significado="autor")
        with pytest.raises(IntegrityError):
            s.add(DeclaracionCarpeta(id=uuid4(), declaracion_id=v.declaracion_id, version=2,
                                     contexto_raiz="Comics/Autor", incluir_descendientes=False,
                                     tipo_de_significado=TipoSignificadoCarpeta.AUTOR,
                                     origen=OrigenRegla.LOCAL, estado=EstadoRegla.ACTIVA,
                                     vigente_desde=__import__("datetime").datetime.now(__import__("datetime").UTC)))
            await s.commit()
        await s.rollback()
