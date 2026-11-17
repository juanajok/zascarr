"""Lector de tebeos CBZ (BL-LEC1, #824).

Solo lee archivos que el contrato #307 decide que son ZIP; un RAR real queda fuera
hasta BL-LEC4. No escribe en el archivo, no usa red y no depende de `Request`: el
router y OPDS-PSE (BL-LEC5) comparten estas funciones.
"""
from __future__ import annotations

import asyncio
import hashlib
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.formato_contenedor import (
    IMAGE_EXTS,
    MAX_ENTRADAS,
    EntradaNoLegible,
    firma_de,
    leer_acotado,
    natural_key,
    se_lee_como_zip,
)
from zascarr.models import File, Issue, ReadingProgress, ReadingStatus
from zascarr.utils.cover import puede_dar_portada


class LectorError(Exception):
    """No se puede abrir el archivo; el mensaje es para el coleccionista."""


class PaginaFueraDeRangoError(LectorError):
    pass


class ArchivoNoLegibleError(LectorError):
    pass


@dataclass(frozen=True)
class ArchivoDeLectura:
    id: str
    nombre: str
    formato: str


@dataclass(frozen=True)
class RecursoPagina:
    datos: bytes
    content_type: str
    etag: str


_CT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
}


def _extension(f: File) -> str:
    if f.file_format is not None:
        return f".{f.file_format.value.lower()}"
    return Path(f.file_name).suffix.lower()


def _es_legible(f: File) -> bool:
    fc = (f.metadata_ or {}).get("formato_contenido")
    ext = _extension(f)
    resultado = puede_dar_portada(ext, fc)
    if resultado is None:
        return ext in (".cbz", ".zip")
    return bool(resultado)


async def archivos_legibles(db: AsyncSession, issue_id: UUID) -> list[ArchivoDeLectura]:
    filas = list((await db.execute(
        select(File).where(File.issue_id == issue_id, File.is_missing.is_(False))
        .order_by(File.file_name)
    )).scalars().all())
    return [ArchivoDeLectura(str(f.id), f.file_name,
                             (f.file_format.value.upper() if f.file_format else "?"))
            for f in filas if _es_legible(f)]


async def archivo_por_defecto(db: AsyncSession, issue_id: UUID) -> ArchivoDeLectura | None:
    legibles = await archivos_legibles(db, issue_id)
    if not legibles:
        return None
    progreso = (await db.execute(
        select(ReadingProgress).where(ReadingProgress.issue_id == issue_id)
    )).scalar_one_or_none()
    if progreso is not None and progreso.file_id:
        for a in legibles:
            if a.id == str(progreso.file_id):
                return a
    return legibles[0]


async def _abrir(db: AsyncSession, file_id: UUID) -> File:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        raise ArchivoNoLegibleError("Ese archivo no está vinculado a un número.")
    if f.is_missing:
        raise ArchivoNoLegibleError("Ese archivo no está disponible en el disco.")
    if not _es_legible(f):
        raise ArchivoNoLegibleError(
            "Este archivo no se puede leer todavía: es un RAR real. "
            "La lectura de CBR llegará en una próxima entrega.")
    return f


def _listado(path: Path) -> list[zipfile.ZipInfo]:
    if not path.is_file():
        raise ArchivoNoLegibleError("El archivo no está en el disco.")
    ext = path.suffix.lower()
    try:
        firma = firma_de(path)
    except OSError as exc:
        raise ArchivoNoLegibleError("No se pudo leer el archivo.") from exc
    if not se_lee_como_zip(ext, firma):
        raise ArchivoNoLegibleError("Este archivo no es un tebeo ZIP legible.")
    try:
        with zipfile.ZipFile(path) as zf:
            infos = [i for i in zf.infolist()
                     if not i.is_dir() and Path(i.filename).suffix.lower() in IMAGE_EXTS
                     and Path(i.filename).name.lower() not in (
                         "thumbs.db", ".ds_store", "desktop.ini", "comicinfo.xml")]
    except (OSError, zipfile.BadZipFile, ValueError, NotImplementedError) as exc:
        raise ArchivoNoLegibleError("El archivo está dañado o incompleto.") from exc
    if len(infos) > MAX_ENTRADAS:
        raise ArchivoNoLegibleError(
            "El archivo tiene demasiadas páginas para abrirlo con seguridad.")
    infos.sort(key=lambda i: natural_key(i.filename))
    if not infos:
        raise ArchivoNoLegibleError("El archivo no tiene páginas de imagen.")
    return infos


def _leer_pagina(path: Path, n: int) -> RecursoPagina:
    infos = _listado(path)
    if n < 1 or n > len(infos):
        raise PaginaFueraDeRangoError("Esa página no existe.")
    info = infos[n - 1]
    try:
        with zipfile.ZipFile(path) as zf:
            datos = leer_acotado(zf, info)
    except (EntradaNoLegible, OSError, zipfile.BadZipFile) as exc:
        raise ArchivoNoLegibleError("No se pudo leer esa página del archivo.") from exc
    extension = Path(info.filename).suffix.lower()
    return RecursoPagina(datos, _CT.get(extension, "application/octet-stream"), "")


def _etag(f: File, n: int, path: Path) -> str:
    if f.sha256_hash:
        base = f.sha256_hash
    elif f.file_mtime_ns:
        base = str(f.file_mtime_ns)
    else:
        try:
            base = str(path.stat().st_mtime_ns)
        except OSError:
            base = hashlib.sha256(str(path).encode()).hexdigest()
    return f'"{base}-{n}"'


async def pagina(db: AsyncSession, file_id: UUID, n: int) -> RecursoPagina:
    f = await _abrir(db, file_id)
    path = Path(f.file_path)
    if not path.is_file():
        raise ArchivoNoLegibleError("El archivo no está en el disco.")
    recurso = await asyncio.to_thread(_leer_pagina, path, n)
    return RecursoPagina(recurso.datos, recurso.content_type, _etag(f, n, path))


async def total_paginas(db: AsyncSession, file_id: UUID) -> int:
    f = await _abrir(db, file_id)
    return len(await asyncio.to_thread(_listado, Path(f.file_path)))


async def guardar_progreso(db: AsyncSession, file_id: UUID, n: int) -> None:
    f = await _abrir(db, file_id)
    total = len(await asyncio.to_thread(_listado, Path(f.file_path)))
    n = max(1, min(int(n), total))
    progreso = (await db.execute(
        select(ReadingProgress).where(ReadingProgress.issue_id == f.issue_id)
    )).scalar_one_or_none()
    if progreso is None:
        progreso = ReadingProgress(issue_id=f.issue_id, status=ReadingStatus.READING)
        db.add(progreso)
    progreso.file_id = f.id
    progreso.current_page = n
    if progreso.status is ReadingStatus.UNREAD:
        progreso.status = ReadingStatus.READING
    if progreso.started_at is None:
        progreso.started_at = datetime.now(UTC)
    await db.flush()
    await db.commit()


async def numero_de(db: AsyncSession, file_id: UUID) -> Issue | None:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        return None
    return await db.get(Issue, f.issue_id)
