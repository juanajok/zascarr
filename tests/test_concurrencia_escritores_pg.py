# ruff: noqa: E501, F811
"""#545 F1: tagger vs «Mantener lo mío» / rescan. El tagger relee tras el lock y el lock
de metadata vive hasta el commit de la sesión que escribe.

Las pruebas usan el mundo de rescan (Postgres + CBZ de verdad). Las de mutación desactivan
`bloquear_archivo` para demostrar que el lock es lo que evita perder `mantenida`/la marca.
"""
from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import pytest

from tests.test_rescan_biblioteca_pg import (  # noqa: F401  (fixtures/ayudas)
    _cbz,
    _filas,
    _rescan,
    mundo,
    url_bd,
)
from tests.test_rescan_relacion_confirmada_pg import (  # noqa: F401
    SECRETO,
    _crear_relacion,
    _discrepancias,
)
from zascarr.models import File
from zascarr.services import discrepancias as discrepancias_mod
from zascarr.services import tagger as tagger_mod
from zascarr.services.discrepancias import mantener_lo_mio
from zascarr.services.tagger import TaggerService
from zascarr.services.tokens_revision import MantenerFirmada, crear_token_mantener
from zascarr.utils.cbz import leer_comicinfo

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


async def _mantener(mundo, token):
    async with mundo.fabrica() as s:
        return await mantener_lo_mio(s, token, secret=SECRETO)


def _token(file_id, d):
    return crear_token_mantener(MantenerFirmada(
        file_id=str(file_id), clave=d["clave"], issue_id=d["relacion"]["issue_id"],
        serie_id=d["relacion"]["serie_id"], vinculo_operacion=d["relacion"]["operacion_id"],
        operacion=str(uuid4()),
    ), SECRETO)


async def _tagger_y_commit(mundo, file_id):
    async with mundo.fabrica() as s:
        archivo = await s.get(File, UUID(str(file_id)))
        r = await TaggerService(s).ejecutar(archivo, dry_run=False)
        # Simula el commit del llamante (CLI de etiquetado): el lock de la sesión
        # sigue vivo hasta aquí.
        await s.commit()
        return r


def _pausar_escribir(monkeypatch):
    entro = asyncio.Event()
    seguir = asyncio.Event()
    original = tagger_mod.TaggerService._escribir

    async def pausa(self, *args, **kwargs):
        entro.set()
        await seguir.wait()
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(tagger_mod.TaggerService, "_escribir", pausa)
    return entro, seguir


async def test_tagger_relee_la_fila_y_no_pierde_mantenida(mundo):
    """El `File` cargado antes del lock no sirve: tras el lock se relee y conserva `mantenida`."""
    ruta, file_id, issue_actual, _ = await _crear_relacion(mundo)
    await _rescan(mundo)
    fila = (await _filas(mundo))[str(ruta)]
    (d,) = _discrepancias(fila)

    async with mundo.fabrica() as s_tagger:
        # Objeto deliberadamente viejo: se carga ANTES de que «Mantener» confirme.
        archivo_viejo = await s_tagger.get(File, UUID(str(file_id)))
        assert _discrepancias(archivo_viejo)[0]["estado"] == "pendiente"
        r = await _mantener(mundo, _token(file_id, d))
        assert r.resultado == "mantenida"

        await TaggerService(s_tagger).ejecutar(archivo_viejo, dry_run=False)
        await s_tagger.commit()

    fila = (await _filas(mundo))[str(ruta)]
    assert _discrepancias(fila)[0]["estado"] == "mantenida"  # no la pisó el metadata viejo
    assert fila.metadata_.get("comicinfo_estado") is not None
    assert str(fila.issue_id) == issue_actual


async def test_mantener_espera_al_tagger_y_no_pierde_su_marca(mundo, monkeypatch):
    """El lock de metadata del tagger cubre hasta el commit: «Mantener» espera y luego conserva la marca."""
    ruta, file_id, issue_actual, _ = await _crear_relacion(mundo)
    await _rescan(mundo)
    d = _discrepancias((await _filas(mundo))[str(ruta)])[0]
    token = _token(file_id, d)

    entro, seguir = _pausar_escribir(monkeypatch)
    tarea_tagger = asyncio.create_task(_tagger_y_commit(mundo, file_id))
    await asyncio.wait_for(entro.wait(), 10)
    tarea_mantener = asyncio.create_task(_mantener(mundo, token))
    try:
        await asyncio.sleep(0.4)
        assert not tarea_mantener.done(), "«Mantener» debe esperar el lock del tagger"
    finally:
        seguir.set()
    await tarea_tagger
    resultado = await tarea_mantener

    assert resultado.resultado == "mantenida"
    fila = (await _filas(mundo))[str(ruta)]
    assert _discrepancias(fila)[0]["estado"] == "mantenida"
    assert fila.metadata_.get("comicinfo_estado") is not None
    assert str(fila.issue_id) == issue_actual


async def test_mutacion_sin_lock_se_pierde_mantenida(mundo, monkeypatch):
    """Mutación: si el advisory no se toma, «Mantener» corre durante la pausa del tagger y el
    flush posterior del tagger pisa `mantenida`. Este test fija el mecanismo que evita el bug."""
    ruta, file_id, _, _ = await _crear_relacion(mundo)
    await _rescan(mundo)
    d = _discrepancias((await _filas(mundo))[str(ruta)])[0]
    token = _token(file_id, d)

    async def _noop(db, file_id):  # noqa: ANN001
        return None

    monkeypatch.setattr(tagger_mod, "bloquear_archivo", _noop)
    monkeypatch.setattr(discrepancias_mod, "bloquear_archivo", _noop)
    entro, seguir = _pausar_escribir(monkeypatch)
    tarea_tagger = asyncio.create_task(_tagger_y_commit(mundo, file_id))
    await asyncio.wait_for(entro.wait(), 10)
    tarea_mantener = asyncio.create_task(_mantener(mundo, token))
    try:
        resultado = await asyncio.wait_for(tarea_mantener, 5)  # sin lock NO espera
        assert resultado.resultado == "mantenida"
    finally:
        seguir.set()
    await tarea_tagger

    fila = (await _filas(mundo))[str(ruta)]
    # Sin lock, el tagger escribió su copia (leída antes de «Mantener») y perdió la decisión.
    assert _discrepancias(fila)[0]["estado"] != "mantenida"


async def test_rescan_espera_al_tagger_y_conserva_su_marca(mundo, monkeypatch):
    """Rescan y tagger comparten lock por File.id; el rescan no pisa el metadata del tagger."""
    ruta, file_id, issue_actual, _ = await _crear_relacion(mundo)
    await _rescan(mundo)

    entro, seguir = _pausar_escribir(monkeypatch)
    tarea_tagger = asyncio.create_task(_tagger_y_commit(mundo, file_id))
    await asyncio.wait_for(entro.wait(), 10)
    _cbz(ruta, "contenido-cambiado-mientras-el-tagger-escribe")
    tarea_rescan = asyncio.create_task(_rescan(mundo))
    try:
        await asyncio.sleep(0.4)
        assert not tarea_rescan.done(), "el rescan debe esperar el lock del tagger"
    finally:
        seguir.set()
    await tarea_tagger
    informe = await tarea_rescan

    fila = (await _filas(mundo))[str(ruta)]
    assert informe.re_triados_protegidos == 1
    # El rescan no reescribe archivos: el ComicInfo que escribió el tagger sigue ahí. La marca
    # `comicinfo_estado` sí se retira a propósito (los bytes cambiaron y ya no la describen).
    assert leer_comicinfo(ruta) is not None
    assert str(fila.issue_id) == issue_actual
