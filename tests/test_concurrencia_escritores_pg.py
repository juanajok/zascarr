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
from sqlalchemy import select

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
from zascarr.models import File, FileFormat, Issue, Series
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


async def _tagger_dos(mundo, ids):
    async with mundo.fabrica() as s:
        informe = await TaggerService(s).run(limit=0, dry_run=False, file_ids=ids)
        await s.commit()
        return informe


async def _dos_archivos_con_orden_opuesto(mundo):
    """Dos ficheros con `File.id` en orden OPUESTO al de su ruta.

    Path: «Serie Ida» < «Serie Zeta». Id: Zeta (1) < Ida (2). Así se puede
    comprobar que tagger y rescan piden los locks en el mismo orden (id), no en
    el suyo natural (imported_at en tagger, ruta en rescan).
    """
    creados = []
    for titulo, numero, ident in (("Serie Zeta", "01", 1), ("Serie Ida", "01", 2)):
        serie = Series(id=uuid4(), title=titulo, start_year=2010)
        issue = Issue(id=uuid4(), series_id=serie.id, issue_number=numero, volume=1)
        ruta = mundo.lib / "Nuevos" / f"{titulo} {numero}.cbz"
        ruta.parent.mkdir(parents=True, exist_ok=True)
        contenido = _cbz(ruta, f"base-{ident}")
        mundo.contenido[ruta] = contenido
        fila = File(
            id=UUID(int=ident), file_path=str(ruta), file_name=ruta.name,
            file_format=FileFormat.CBZ, file_size_bytes=len(contenido),
            sha256_hash=None, file_mtime_ns=None, issue_id=issue.id,
            metadata_={"match_status": "unsorted"},
        )
        async with mundo.fabrica() as s:
            s.add(serie)
            s.add(issue)
            s.add(fila)
            await s.commit()
        creados.append((fila.id, ruta))
    # Primera pasada: fija la línea de base del resto de la biblioteca y de estos dos.
    await _rescan(mundo)
    # Los dos cambian: la siguiente pasada los re-tria (y el tagger los etiqueta).
    for ident, ruta in creados:
        mundo.contenido[ruta] = _cbz(ruta, f"cambio-{ident}")
    # Fuerza la línea de base vieja: no depender de la resolución de mtime ni del tamaño del ZIP.
    async with mundo.fabrica() as s:
        for fila in (await s.execute(select(File).where(File.id.in_([UUID(int=1), UUID(int=2)])))).scalars().all():
            fila.file_mtime_ns = None
        await s.commit()
    return [str(i) for i, _ in creados], [r for _, r in creados]


async def test_multifile_tagger_y_rescan_con_ordenes_opuestos_no_se_bloquean(mundo):
    ids, rutas = await _dos_archivos_con_orden_opuesto(mundo)
    assert [str(r) for r in sorted(rutas)] == [str(rutas[1]), str(rutas[0])]   # ruta: Ida, Zeta
    assert ids == [str(UUID(int=1)), str(UUID(int=2))]                          # id: Zeta, Ida

    tarea_tagger = asyncio.create_task(_tagger_dos(mundo, ids))
    tarea_rescan = asyncio.create_task(_rescan(mundo))
    try:
        _, informe = await asyncio.wait_for(asyncio.gather(tarea_tagger, tarea_rescan), 25)
    finally:
        for t in (tarea_tagger, tarea_rescan):
            t.cancel()
        await asyncio.gather(tarea_tagger, tarea_rescan, return_exceptions=True)
    assert informe is not None


async def test_mutacion_sin_orden_global_bloquea_tagger_y_rescan(mundo, monkeypatch):
    """Mutación: rescan vuelve a ordenar por RUTA (el orden viejo). Con tagger por
    `File.id` y rutas en orden opuesto, cada uno toma A/B al revés y se bloquean.
    La prueba normal de arriba falla si vuelve ese orden."""
    import zascarr.services.library_adopter as adopter

    await _dos_archivos_con_orden_opuesto(mundo)
    monkeypatch.setattr(adopter, "_clave_de_orden_de_retriaje", lambda t: str(t[0]))

    original_bloqueo = adopter.bloquear_archivo
    ida = str(UUID(int=2))
    zeta = str(UUID(int=1))
    rescan_tiene_ida = asyncio.Event()
    rescan_intenta_zeta = asyncio.Event()

    async def _espia(db, file_id):
        if str(file_id) == zeta:
            # Se marca ANTES de bloquearse: el rescan ya va a pedir el lock de Zeta,
            # que tiene el tagger; si no hay orden global, se cierra el ciclo.
            rescan_intenta_zeta.set()
        await original_bloqueo(db, file_id)
        if str(file_id) == ida:
            rescan_tiene_ida.set()

    monkeypatch.setattr(adopter, "bloquear_archivo", _espia)

    entro, seguir = _pausar_escribir(monkeypatch)
    tarea_tagger = asyncio.create_task(_tagger_dos(mundo, [str(UUID(int=1)), str(UUID(int=2))]))
    await asyncio.wait_for(entro.wait(), 10)              # tagger tiene Zeta (id 1)
    tarea_rescan = asyncio.create_task(_rescan(mundo))
    await asyncio.wait_for(rescan_tiene_ida.wait(), 10)   # rescan tiene Ida (ruta 1)
    await asyncio.wait_for(rescan_intenta_zeta.wait(), 10)  # y quiere Zeta, que tiene el tagger
    seguir.set()                                          # tagger va a por Ida, que tiene el rescan
    try:
        tag, res = await asyncio.wait_for(asyncio.gather(tarea_tagger, tarea_rescan), 15)
    finally:
        for t in (tarea_tagger, tarea_rescan):
            t.cancel()
        await asyncio.gather(tarea_tagger, tarea_rescan, return_exceptions=True)
    # El detector de Postgres puede abortar a cualquiera de los dos; el servicio
    # de rescan captura el error y lo anota. Lo que NO puede pasar es que ambos
    # terminen limpios: eso significaría que el orden mutado no provoca el ciclo.
    assert res.errores or tag.abortado is not None or tag.escritos < 2
