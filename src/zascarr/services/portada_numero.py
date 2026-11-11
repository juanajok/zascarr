"""BL-INF4 (#590): miniatura de la portada de un número, cacheada por archivo.

La usan la vista previa al pasar el ratón por los chips de la ficha (esta historia) y, más
adelante, el selector de portada (BL-INF6) y las tarjetas de Biblioteca (BL-INF7).

- **Sin red**: la portada sale del propio archivo del número (ZIP por contenido, RAR con `unar`
  a través del turno único y los topes de #418).
- **Caché por `File.id`** en `<covers>/v3/numero/<file_id>.jpg` (240 px, previa) y
  `<file_id>-<ancho>.jpg` (p. ej. 600 px, ficha del número): un número con el mismo archivo
  reutiliza la miniatura; la marca de fallo RAR se invalida por `mtime`/tamaño.
- **Una sola generación por (archivo, ancho)** (lock `asyncio`) y escritura atómica.
- **Respeta `LECTOR_RAR_ENABLED=false`**: con el lector apagado, un RAR no es candidato y no se
  envía a `lsar`/`unar` (ADR-0015, FR-34 de BL-PORT3).
- No escribe en la biblioteca ni en la base de datos.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import time
from pathlib import Path
from uuid import UUID
from weakref import WeakValueDictionary

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, Issue
from zascarr.utils.cover import CACHE_VERSION, es_candidato_de_portada, extract_cover_thumbnail
from zascarr.utils.espacio import comprobar_espacio
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

#: Ancho de la miniatura de la vista previa (hover/foco).
ANCHO_PREVIA = 240
#: Ancho de la portada en la ficha del número (mismo tamaño que la portada de serie).
ANCHO_FICHA = 600
#: Archivos que se miran como mucho por número (hay números con varias ediciones/archivos).
MAX_ARCHIVOS_NUMERO = 3
#: Tope de tiempo para no bloquear un hover con una serie de CBR lentos.
PRESUPUESTO_PREVIA_S = 6.0
#: Presupuesto de memoria por miniatura: una página de 40 Mpx no se decodifica para 240 px.
MAX_PIXELES_PREVIA = 6_000_000
MAX_PIXELES_FICHA = 12_000_000
#: Generaciones simultáneas como máximo en todo el proceso.
_GENERACIONES = asyncio.Semaphore(2)

#: Un lock por (archivo, ancho) mientras dura una generación; se libera solo al terminar.
_cerrojos: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()


def _huella(path: Path) -> dict | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return {"tamano": st.st_size, "mtime_ns": st.st_mtime_ns}


def _camino_huella(camino: Path, *, negativa: bool = False) -> Path:
    sufijo = ".sin-portada.json" if negativa else ".json"
    return camino.with_name(camino.name + sufijo)


def _huella_vigente(camino: Path, path: Path, *, negativa: bool = False) -> bool:
    huella = _huella(path)
    if huella is None:
        return False
    try:
        guardada = json.loads(_camino_huella(camino, negativa=negativa).read_text())
    except (OSError, ValueError, TypeError):
        return not negativa
    return (guardada.get("tamano") == huella["tamano"]
            and guardada.get("mtime_ns") == huella["mtime_ns"])


def _escribir_huella(camino: Path, path: Path, *, negativa: bool = False) -> None:
    huella = _huella(path)
    if huella is None:
        return
    try:
        camino.parent.mkdir(parents=True, exist_ok=True)
        _camino_huella(camino, negativa=negativa).write_text(json.dumps(huella))
    except OSError as exc:
        logger.warning("previa.huella_sin_escribir", motivo=type(exc).__name__)


def carpeta_de_previas(settings=None) -> Path:
    return Path((settings or get_settings()).covers_cache_path) / CACHE_VERSION / "numero"


def _camino(carpeta: Path, file_id: UUID, ancho: int) -> Path:
    sufijo = "" if ancho == ANCHO_PREVIA else f"-{ancho}"
    return carpeta / f"{file_id}{sufijo}.jpg"


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
             settings, ancho: int, max_pixeles: int) -> tuple[bytes, UUID] | None:
    """Extrae la primera página del primer archivo que pueda darla. Sin BD y sin locks: se llama
    desde un hilo. El interruptor del lector de RAR se respeta igual que en `_primera_portada`."""
    covers = Path(settings.covers_cache_path)
    marcas = covers / CACHE_VERSION
    limite = time.monotonic() + PRESUPUESTO_PREVIA_S
    herramienta = None if getattr(settings, "lector_rar_enabled", True) else False
    for file_id, ruta, formato in archivos:
        if time.monotonic() >= limite:
            break
        path = Path(ruta)
        es_rar = es_rar_candidato(path, formato)
        if not es_rar and not es_candidato_de_portada(path, formato):
            continue
        if es_rar:
            if herramienta is False:
                continue
            if herramienta is None:
                herramienta = lector_rar_disponible()
            if not herramienta or marca_vigente(marcas, file_id, path):
                continue
            try:
                datos, _tipo = portada_de_rar(path, covers, ancho=ancho,
                                              max_pixeles=max_pixeles)
                return datos, file_id
            except ErrorRar as exc:
                if exc.motivo in MOTIVOS_DEL_ARCHIVO:
                    escribir_marca(marcas, file_id, path, exc.motivo)
                continue
        resultado = extract_cover_thumbnail(path, formato, ancho=ancho,
                                            max_pixeles=max_pixeles)
        if resultado:
            return resultado[0], file_id
    return None


async def ruta_previa(db: AsyncSession, serie_id: UUID, issue_id: UUID, *,
                      ancho: int = ANCHO_PREVIA, settings=None) -> Path | None:
    """La portada del número (generándola si toca) o `None` si no hay.

    #603: presupuesto y concurrencia acotados (wait_for + semáforo global), consulta de archivos
    corta y conexión liberada antes de esperar el lock, caché invalidada por huella y caché
    negativa para no repetir extracciones sin portada.
    """
    settings = settings or get_settings()
    carpeta = carpeta_de_previas(settings)
    archivos = await _archivos_del_numero(db, serie_id, issue_id)
    if callable(getattr(db, "rollback", None)):
        with contextlib.suppress(Exception):
            await db.rollback()
    if not archivos:
        return None
    for file_id, ruta, _formato in archivos:
        camino = _camino(carpeta, file_id, ancho)
        if camino.is_file() and _huella_vigente(camino, Path(ruta)):
            return camino
    if all(_huella_vigente(_camino(carpeta, fid, ancho), Path(ruta), negativa=True)
           for fid, ruta, _formato in archivos):
        return None
    cerrojo = _cerrojos.setdefault(f"{archivos[0][0]}:{ancho}", asyncio.Lock())
    async with cerrojo:
        for file_id, ruta, _formato in archivos:
            camino = _camino(carpeta, file_id, ancho)
            if camino.is_file() and _huella_vigente(camino, Path(ruta)):
                return camino
        if all(_huella_vigente(_camino(carpeta, fid, ancho), Path(ruta), negativa=True)
               for fid, ruta, _formato in archivos):
            return None
        max_pixeles = MAX_PIXELES_PREVIA if ancho == ANCHO_PREVIA else MAX_PIXELES_FICHA
        try:
            async with _GENERACIONES:
                generado = await asyncio.wait_for(
                    asyncio.to_thread(_generar, archivos, settings, ancho, max_pixeles),
                    timeout=PRESUPUESTO_PREVIA_S)
        except TimeoutError:
            logger.warning("previa.tiempo_agotado", ancho=ancho)
            return None
        if generado is None:
            # Si el lector RAR está apagado, la ausencia es de CONFIGURACIÓN, no del archivo:
            # no se cachea en negativo para que al encenderlo se vuelva a intentar.
            rar_apagado = any(
                es_rar_candidato(Path(ruta), formato)
                for _fid, ruta, formato in archivos
            ) and not getattr(settings, "lector_rar_enabled", True)
            if not rar_apagado:
                for file_id, ruta, _formato in archivos:
                    _escribir_huella(_camino(carpeta, file_id, ancho), Path(ruta), negativa=True)
            return None
        datos, file_id = generado
        try:
            carpeta.mkdir(parents=True, exist_ok=True)
            comprobar_espacio(carpeta, len(datos), "guardar la miniatura")
            fd, temporal = tempfile.mkstemp(prefix=f".{file_id}.", suffix=".jpg", dir=str(carpeta))
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(datos)
                destino = _camino(carpeta, file_id, ancho)
                os.replace(temporal, destino)
            finally:
                with contextlib.suppress(OSError):
                    Path(temporal).unlink(missing_ok=True)
        except OSError as exc:   # disco lleno/permiso: degradar a «sin previa», no 500
            logger.warning("previa.cache_sin_escribir", motivo=type(exc).__name__)
            return None
        for fid, ruta, _formato in archivos:
            _escribir_huella(_camino(carpeta, fid, ancho), Path(ruta))
        return destino
