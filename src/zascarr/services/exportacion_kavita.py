"""B20: exportar una colección a un árbol de carpetas para Kavita.

Nunca escribe ni mueve la biblioteca canónica. Materializa hardlinks (o copia
si el destino está en otro filesystem), escribe un manifiesto atómico y deja
un `ImportRun` auditable. El parche ComicInfo es fase 2 y se rechaza aquí.
"""
from __future__ import annotations

import asyncio
import errno
import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.exportacion_kavita import ArchivoFuente, PlanExportacion, plan_export
from zascarr.models import Collection, File, ImportRun, Issue, Series

logger = structlog.get_logger()

VERSION_MANIFIESTO = 1
NOMBRE_MANIFIESTO = "_zascarr_manifest.json"


class ExportacionError(RuntimeError):
    """Error en llano para la API/UI (no se ha tocado la biblioteca)."""


class ParcheComicInfoNoDisponibleError(ExportacionError):
    """El parche es fase 2: se rechaza antes de tocar nada."""


class EspacioInsuficienteError(ExportacionError):
    pass


@dataclass
class ResumenExportacion:
    run_id: str
    collection_id: str
    destino: str
    materializados: int
    omitidos: int
    colisiones: int
    deriva: int
    errores: int
    bytes_copiados: int
    archivos: list[dict] = field(default_factory=list)
    saltados: int = 0
    modo: str = "hardlink"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _resolver_raiz(settings) -> Path:
    root = Path(settings.export_path)
    crudo = str(root)
    if ".." in Path(crudo).parts:
        raise ExportacionError("La ruta de exportación no puede contener «..».")
    actual = root
    while actual != actual.parent:
        if actual.is_symlink():
            raise ExportacionError("La raíz de exportación no puede contener symlinks.")
        actual = actual.parent
    resuelta = root.resolve()
    prohibidas = [
        getattr(settings, "library_path", None),
        getattr(settings, "downloads_path", None),
        getattr(settings, "amule_incoming_dir", None),
    ]
    prohibidas += list(getattr(settings, "carpetas_compartidas", None) or [])
    for p in prohibidas:
        if not p:
            continue
        try:
            objetivo = Path(p).resolve()
        except OSError:
            continue
        if resuelta == objetivo or resuelta.is_relative_to(objetivo):
            raise ExportacionError(
                "La raíz de exportación no puede estar dentro de la biblioteca, "
                "descargas, incoming ni una carpeta compartida.")
    return resuelta


def _comprobar_sin_symlinks(destino: Path, root: Path) -> None:
    actual = destino
    while actual != root and actual != actual.parent:
        if actual.exists() and actual.is_symlink():
            raise ExportacionError("El destino contiene un symlink: no se exporta ahí.")
        actual = actual.parent


async def _filas(db: AsyncSession, collection: Collection) -> list[ArchivoFuente]:
    filas = (await db.execute(
        select(Series, Issue, File)
        .join(Issue, Issue.series_id == Series.id)
        .join(File, File.issue_id == Issue.id)
        .where(Series.collection_id == collection.id)
        .order_by(Series.sort_title, Issue.sort_order, Issue.issue_number, File.file_path)
    )).all()
    salida: list[ArchivoFuente] = []
    for serie, issue, archivo in filas:
        salida.append(ArchivoFuente(
            file_id=str(archivo.id), issue_id=str(issue.id), series_id=str(serie.id),
            series_title=serie.title, numero=issue.issue_number,
            issue_title=issue.title, source_path=archivo.file_path,
            size_bytes=int(archivo.file_size_bytes or 0),
            sha256=archivo.sha256_hash, is_missing=bool(archivo.is_missing),
            form=issue.format.value if hasattr(issue.format, "value") else str(issue.format)))
    return salida


def _plan(collection: Collection, fuentes: list[ArchivoFuente], root: Path) -> PlanExportacion:
    return plan_export(fuentes, root, folder=collection.name)


def _marcar_fuentes(fuentes: list[ArchivoFuente]) -> list[ArchivoFuente]:
    """Fuera del bucle async: comprueba symlinks/fuentes inexistentes."""
    salida: list[ArchivoFuente] = []
    for f in fuentes:
        ruta = Path(f.source_path)
        try:
            raro = ruta.is_symlink() or not ruta.exists()
        except OSError:
            raro = True
        salida.append(f if not raro else type(f)(**{**f.__dict__, "is_missing": True}))
    return salida


def _materializar(
    plan: PlanExportacion, root: Path,
) -> tuple[list[dict], int, int, int, int, int, str]:
    entradas: list[dict] = []
    omitidos = len(plan.omitidos) + len(plan.colisiones)
    colisiones = len(plan.colisiones)
    deriva = 0
    errores = 0
    copiados = 0
    modos: set[str] = set()
    # Preflight: suma de lo que necesitará copia forzada por filesystem distinto.
    previstos: list[tuple[object, Path, str]] = []
    for accion in plan.archivos:
        destino = (root / accion.destino_relativo)
        padre = destino.parent
        _comprobar_sin_symlinks(destino, root)
        padre.mkdir(parents=True, exist_ok=True)
        modo = ("copy" if Path(accion.source_path).stat().st_dev != padre.stat().st_dev
                else "hardlink")
        previstos.append((accion, destino, modo))
    copias_previstas = sum(a.size_bytes for a, _d, m in previstos if m == "copy")
    if copias_previstas:
        libre = shutil.disk_usage(root).free
        if libre < copias_previstas:
            raise EspacioInsuficienteError(
                f"No hay espacio suficiente en {root}: "
                f"faltan {copias_previstas - libre} bytes.")
    for accion, destino, modo in previstos:
        try:
            if destino.exists():
                sha_destino = _sha256(destino)
                if sha_destino == (accion.sha256 or _sha256(Path(accion.source_path))):
                    entradas.append({
                        "dest": accion.destino_relativo.replace("\\", "/"),
                        "sha256": sha_destino, "issue_id": accion.issue_id,
                        "file_id": accion.file_id, "mode": "skip", "status": "skip",
                    })
                    continue
                deriva += 1
                continue
            destino.parent.mkdir(parents=True, exist_ok=True)
            if modo == "hardlink":
                try:
                    os.link(accion.source_path, destino)
                except OSError as exc:
                    if exc.errno != errno.EXDEV:
                        raise
                    modo = "copy"
            if modo == "copy":
                libre = shutil.disk_usage(destino.parent).free
                if libre < accion.size_bytes:
                    raise EspacioInsuficienteError(
                        "No hay espacio suficiente para copiar la exportación.")
                # Temporal único en el mismo directorio; se publica con link
                # (falla si el destino apareció) para no sobrescribir jamás.
                fd, temp = tempfile.mkstemp(prefix=f".{destino.name}.", dir=str(destino.parent))
                os.close(fd)
                try:
                    shutil.copy2(accion.source_path, temp)
                    # Publicación sin pisar: crear el destino en exclusiva y
                    # copiar el temporal ya verificado. No se usa `os.replace`.
                    fd = os.open(destino, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                    with os.fdopen(fd, "wb") as salida, Path(temp).open("rb") as entrada:
                        shutil.copyfileobj(entrada, salida)
                    shutil.copystat(accion.source_path, destino)
                finally:
                    Path(temp).unlink(missing_ok=True)
                copiados += accion.size_bytes
            sha = accion.sha256 or _sha256(destino)
            modos.add(modo)
            entradas.append({
                "dest": accion.destino_relativo.replace("\\", "/"),
                "sha256": sha, "issue_id": accion.issue_id,
                "file_id": accion.file_id, "mode": modo, "status": "ok",
            })
        except EspacioInsuficienteError:
            raise
        except Exception:
            errores += 1
            logger.exception("exportacion_kavita.materializar_falló", destino=str(destino))
    modo_global = "mixed" if len(modos) > 1 else (next(iter(modos)) if modos else "hardlink")
    return entradas, omitidos, colisiones, deriva, errores, copiados, modo_global

def _escribir_manifiesto(plan: PlanExportacion, root: Path, collection: Collection,
                         files: list[dict], modo: str) -> Path:
    carpeta = root / plan.folder
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / NOMBRE_MANIFIESTO
    datos = {
        "zascarr_version": "1",
        "manifest_version": VERSION_MANIFIESTO,
        "collection_id": str(collection.id),
        "collection_name": collection.name,
        "exported_at": datetime.now(UTC).isoformat(),
        "mode": modo,
        "files": files,
    }
    fd, temp = tempfile.mkstemp(prefix=".zascarr_manifest.", dir=str(carpeta))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, destino)
    finally:
        Path(temp).unlink(missing_ok=True)
    return destino


async def exportar_coleccion(db: AsyncSession, collection_id: UUID, *,
                             patch_comicinfo: bool = False) -> ResumenExportacion:
    if patch_comicinfo:
        raise ParcheComicInfoNoDisponibleError(
            "El parche de ComicInfo todavía no está disponible: es la fase 2 de esta función. "
            "Exporta sin parche; no se toca ningún archivo.")
    collection = await db.get(Collection, collection_id)
    if collection is None:
        raise ExportacionError("La colección ya no existe.")
    if collection.auto_search is None:  # defensa: la columna es NOT NULL
        raise ExportacionError("La colección no es válida.")
    settings = get_settings()
    root = await asyncio.to_thread(_resolver_raiz, settings)
    await asyncio.to_thread(root.mkdir, parents=True, exist_ok=True)
    try:
        fuentes = await _filas(db, collection)
    except Exception as exc:
        raise ExportacionError(f"No se pudo leer la colección: {exc}") from exc
    fuentes = await asyncio.to_thread(_marcar_fuentes, fuentes)
    plan = await asyncio.to_thread(_plan, collection, fuentes, root)
    await asyncio.to_thread((root / plan.folder).mkdir, parents=True, exist_ok=True)
    (archivos, omitidos, colisiones, deriva, errores,
     copiados, modo) = await asyncio.to_thread(_materializar, plan, root)
    manifiesto = await asyncio.to_thread(
        _escribir_manifiesto, plan, root, collection, archivos, modo)
    ahora = datetime.now(UTC)
    materializados_ok = sum(1 for a in archivos if a.get("status") == "ok")
    saltados = sum(1 for a in archivos if a.get("status") == "skip")
    run = ImportRun(
        id=uuid4(), started_at=ahora, finished_at=ahora,
        files_scanned=len(fuentes), imported_count=materializados_ok,
        duplicate_count=saltados, unsorted_count=omitidos,
        error_count=errores + deriva,
        details={
            "kind": "export", "collection_id": str(collection.id),
            "collection_name": collection.name, "root": str(root),
            "manifest": str(manifiesto), "archivos": archivos,
            "omitidos": plan.omitidos, "colisiones": plan.colisiones,
            "deriva": deriva, "bytes_copiados": copiados, "mode": modo,
            "saltados": saltados,
        })
    db.add(run)
    await db.flush()
    return ResumenExportacion(
        run_id=str(run.id), collection_id=str(collection.id), destino=str(root / plan.folder),
        materializados=materializados_ok, omitidos=omitidos, colisiones=colisiones,
        deriva=deriva, errores=errores, bytes_copiados=copiados, archivos=archivos,
        saltados=saltados, modo=modo)
