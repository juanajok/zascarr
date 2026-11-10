"""BL-INF4 (#590): miniatura de la portada de un número, cacheada por archivo.

La usan la vista previa al pasar el ratón por los chips de la ficha (esta historia) y, más
adelante, el selector de portada (BL-INF6) y las tarjetas de Biblioteca (BL-INF7).

- **Sin red**: la portada sale del propio archivo del número (ZIP por contenido, RAR con `unar`
  a través del turno único y los topes de #418).
- **Caché por `File.id`** en `<covers>/v3/numero/<file_id>.jpg`: un número con el mismo archivo
  reutiliza la miniatura; un archivo sustituido la invalida por la marca de fallo con `mtime`.
- **Una sola generación por archivo** (lock `asyncio`) y escritura atómica.
- No escribe en la biblioteca ni en la base de datos.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
import time
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, Issue
from zascarr.utils.cover import CACHE_VERSION, es_candidato_de_portada, extract_cover_thumbnail
from zascarr.utils.lector_rar import ErrorRar
from zascarr.utils.lector_rar import disponible as lector_rar_disponible
from zascarr.utils.portada_rar import (
    MOTIVOS_DEL_ARCHIVO,
    es_rar_candidato,
    escribir_marca,
    marca_vigente,
    portada_de_rar,
)

logger = structlog.get_logger()

#: Ancho de la miniatura de la vista previa (la portada de serie usa 600).
ANCHO_PREVIA = 240
#: Archivos que se miran como mucho por número (hay números con varias ediciones/archivos).
MAX_ARCHIVOS_NUMERO = 3
#: Tope de tiempo para no bloquear un hover con una serie de CBR lentos.
PRESUPUESTO_PREVIA_S = 6.0

_cerrojos: dict[str, asyncio.Lock] = {}


def carpeta_de_previas(settings=None) -> Path:
    return Path((settings or get_settings()).covers_cache_path) / CACHE_VERSION / "numero"


def _camino(carpeta: Path, file_id: UUID) -> Path:
    return carpeta / f"{file_id}.jpg"


async def _archivos_del_numero(db: AsyncSession, serie_id: UUID,
                               issue_id: UUID) -> list[tuple[UUID, str, dict | None]]:
    filas = (await db.execute(
        select(File.id, File.file_path, File.metadata_["formato_contenido"])
        .join(Issue, File.issue_id == Issue.id)
        .where(Issue.id == issue_id, Issue.series_id == serie_id, File.is_missing.is_(False))
        .order_by(File.file_path)
        .limit(MAX_ARCHIVOS_NUMERO)
    )).all()
    return [(fid, str(ruta), formato) for fid, ruta, formato in filas]


def _generar(archivos: list[tuple[UUID, str, dict | None]],
             settings) -> tuple[bytes, UUID] | None:
    """Extrae la primera página del primer archivo que pueda darla. Sin BD y sin locks: se llama
    desde un hilo."""
    covers = Path(settings.covers_cache_path)
    marcas = covers / CACHE_VERSION
    limite = time.monotonic() + PRESUPUESTO_PREVIA_S
    for file_id, ruta, formato in archivos:
        if time.monotonic() >= limite:
            break
        path = Path(ruta)
        es_rar = es_rar_candidato(path, formato)
        if not es_rar and not es_candidato_de_portada(path, formato):
            continue
        if es_rar:
            if not lector_rar_disponible() or marca_vigente(marcas, file_id, path):
                continue
            try:
                datos, _tipo = portada_de_rar(path, covers, ancho=ANCHO_PREVIA)
                return datos, file_id
            except ErrorRar as exc:
                if exc.motivo in MOTIVOS_DEL_ARCHIVO:
                    escribir_marca(marcas, file_id, path, exc.motivo)
                continue
        resultado = extract_cover_thumbnail(path, formato, ancho=ANCHO_PREVIA)
        if resultado:
            return resultado[0], file_id
    return None


async def ruta_previa(db: AsyncSession, serie_id: UUID, issue_id: UUID, *,
                      settings=None) -> Path | None:
    """La miniatura del número (generándola si toca) o `None` si no hay portada."""
    settings = settings or get_settings()
    carpeta = carpeta_de_previas(settings)
    archivos = await _archivos_del_numero(db, serie_id, issue_id)
    if not archivos:
        return None
    for file_id, _ruta, _formato in archivos:
        camino = _camino(carpeta, file_id)
        if camino.is_file():
            return camino
    cerrojo = _cerrojos.setdefault(str(archivos[0][0]), asyncio.Lock())
    async with cerrojo:
        for file_id, _ruta, _formato in archivos:
            camino = _camino(carpeta, file_id)
            if camino.is_file():
                return camino
        generado = await asyncio.to_thread(_generar, archivos, settings)
        if generado is None:
            return None
        datos, file_id = generado
        carpeta.mkdir(parents=True, exist_ok=True)
        fd, temporal = tempfile.mkstemp(prefix=f".{file_id}.", suffix=".jpg", dir=str(carpeta))
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(datos)
            os.replace(temporal, _camino(carpeta, file_id))
        finally:
            with contextlib.suppress(OSError):
                Path(temporal).unlink(missing_ok=True)
        return _camino(carpeta, file_id)
