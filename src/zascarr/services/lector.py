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

from zascarr.config import get_settings
from zascarr.core.comicinfo_write import MAX_COMICINFO_BYTES
from zascarr.core.formato_contenedor import (
    IMAGE_EXTS,
    MAX_ENTRADAS,
    EntradaNoLegible,
    firma_de,
    leer_acotado,
    motivo_fuera_de_limite,
    natural_key,
    se_lee_como_zip,
)
from zascarr.core.importer_triage import parse_comic_info
from zascarr.models import File, Firma, Issue, IssueFormat, ReadingProgress, ReadingStatus, Series
from zascarr.services.cache_lectura import CacheError, CacheLectura
from zascarr.services.series import huecos_de_serie, numero_de_grapa, numeros_poseidos
from zascarr.utils.cover import puede_dar_portada


class LectorError(Exception):
    """No se puede abrir el archivo; el mensaje es para el coleccionista."""


class PaginaFueraDeRangoError(LectorError):
    pass


class ArchivoNoLegibleError(LectorError):
    pass


SENTIDOS = {"ltr": "izquierda a derecha", "rtl": "derecha a izquierda"}
#: Una sola caché por proceso: comparte tareas, errores y cuota entre peticiones.
CACHE = CacheLectura.desde_ajustes()


def es_rar_real(f: File) -> bool:
    ext = _extension(f)
    fc = (f.metadata_ or {}).get("formato_contenido") or {}
    if ext not in (".cbr", ".cb7", ".rar"):
        return False
    if fc.get("firma") == "rar":
        return True
    if fc.get("firma") == "zip":
        return False
    # Metadatos antiguos sin formato: se mira la firma (512 B) para no romper los CBR legados.
    try:
        return firma_de(Path(f.file_path)) is Firma.RAR
    except OSError:
        return True


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
    meta = f.metadata_ or {}
    fc = meta.get("formato_contenido")
    ext = _extension(f)
    # La conversión CBR→CBZ cambia `file_format` y la ruta, pero el `formato_contenido`
    # guardado puede seguir diciendo «rar»: el archivo ya es un ZIP y el botón debe salir.
    # La lectura vuelve a comprobar la firma antes de servir una página.
    if ext in (".cbz", ".zip") and (meta.get("conversion") or {}).get("estado") == "convertida":
        return True
    resultado = puede_dar_portada(ext, fc)
    if resultado is None:
        return ext in (".cbz", ".zip", ".cbr", ".cb7")
    if resultado:
        return True
    # BL-LEC4: un CBR/CB7 que es RAR se prepara con `unar` (si el lector está encendido).
    return es_rar_real(f) and get_settings().lector_rar_enabled


async def archivos_legibles(db: AsyncSession, issue_id: UUID) -> list[ArchivoDeLectura]:
    filas = list((await db.execute(
        select(File).where(File.issue_id == issue_id, File.is_missing.is_(False))
        .order_by(File.file_name)
    )).scalars().all())
    return [ArchivoDeLectura(str(f.id), f.file_name,
                             (f.file_format.value.upper() if f.file_format else "?"))
            for f in filas if _es_legible(f)]


def _por_defecto(candidatos: list, file_id_progreso: object):
    """Regla única del archivo por defecto de un número (LEC1 y OPDS-PSE la comparten).

    El archivo con el que se leyó por última vez; si no hay o ya no existe, el primero
    por nombre. `candidatos` ya viene ordenado y solo con archivos legibles.
    """
    if not candidatos:
        return None
    if file_id_progreso:
        for c in candidatos:
            if str(c.id) == str(file_id_progreso):
                return c
    return candidatos[0]


async def archivo_por_defecto(db: AsyncSession, issue_id: UUID) -> ArchivoDeLectura | None:
    legibles = await archivos_legibles(db, issue_id)
    if not legibles:
        return None
    progreso = (await db.execute(
        select(ReadingProgress).where(ReadingProgress.issue_id == issue_id)
    )).scalar_one_or_none()
    return _por_defecto(legibles, progreso.file_id if progreso is not None else None)


async def _abrir(db: AsyncSession, file_id: UUID) -> File:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        raise ArchivoNoLegibleError("Ese archivo no está vinculado a un número.")
    if f.is_missing:
        raise ArchivoNoLegibleError("Ese archivo no está disponible en el disco.")
    ruta = Path(f.file_path)
    if ruta.is_symlink():
        raise ArchivoNoLegibleError("Ese archivo no se puede abrir con seguridad.")
    if not _es_legible(f):
        raise ArchivoNoLegibleError(
            "Este archivo no se puede leer todavía: no es un ZIP de tebeo. "
            "La lectura de CBR llegará en una próxima entrega.")
    return f


def _listado(path: Path) -> list[zipfile.ZipInfo]:
    if path.is_symlink() or not path.is_file():
        raise ArchivoNoLegibleError("El archivo no está en el disco.")
    ext = path.suffix.lower()
    try:
        firma = firma_de(path)
    except OSError as exc:
        raise ArchivoNoLegibleError("No se pudo leer el archivo.") from exc
    if not se_lee_como_zip(ext, firma):
        raise ArchivoNoLegibleError("Este archivo no es un tebeo ZIP legible.")
    if motivo_fuera_de_limite(path) is not None:
        raise ArchivoNoLegibleError(
            "El archivo tiene demasiadas entradas o un índice demasiado grande.")
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
    if es_rar_real(f):
        if not (await asyncio.to_thread(CACHE._paginas, f)):
            raise ArchivoNoLegibleError("El tebeo todavía se está preparando.")
        try:
            datos, content_type = await asyncio.to_thread(CACHE.leer_pagina, f, n)
        except CacheError as exc:
            raise ArchivoNoLegibleError(str(exc)) from exc
        return RecursoPagina(datos, content_type, _etag(f, n, path))
    recurso = await asyncio.to_thread(_leer_pagina, path, n)
    return RecursoPagina(recurso.datos, recurso.content_type, _etag(f, n, path))


async def total_paginas(db: AsyncSession, file_id: UUID) -> int:
    f = await _abrir(db, file_id)
    if es_rar_real(f):
        return len(await asyncio.to_thread(CACHE._paginas, f))
    return len(await asyncio.to_thread(_listado, Path(f.file_path)))


async def guardar_progreso(db: AsyncSession, file_id: UUID, n: int) -> None:
    f = await _abrir(db, file_id)
    if es_rar_real(f):
        paginas = await asyncio.to_thread(CACHE._paginas, f)
        total = len(paginas)
    else:
        total = len(await asyncio.to_thread(_listado, Path(f.file_path)))
    if total == 0:
        raise ArchivoNoLegibleError("El tebeo todavía se está preparando.")
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
    progreso.last_read_at = datetime.now(UTC)
    if progreso.started_at is None:
        progreso.started_at = progreso.last_read_at
    await db.flush()
    await db.commit()


def _manga_del_archivo(path: Path) -> str | None:
    """`<Manga>` del ComicInfo.xml, si el archivo lo trae. Solo lee esa entrada."""
    try:
        with zipfile.ZipFile(path) as zf:
            for info in zf.infolist():
                if Path(info.filename).name.lower() == "comicinfo.xml":
                    if info.file_size > MAX_COMICINFO_BYTES:
                        return None
                    datos = leer_acotado(zf, info, tope=MAX_COMICINFO_BYTES)
                    return parse_comic_info(datos).manga
    except (OSError, zipfile.BadZipFile, EntradaNoLegible, ValueError, SyntaxError):
        return None
    return None


async def sentido_de_lectura(db: AsyncSession, file_id: UUID) -> tuple[str, str]:
    """Devuelve `(sentido, origen)`; prioridad serie > ComicInfo > tradición."""
    f = await _abrir(db, file_id)
    issue = await db.get(Issue, f.issue_id)
    serie = await db.get(Series, issue.series_id) if issue is not None else None
    if serie is not None:
        elegido = (serie.metadata_ or {}).get("lector_sentido")
        if elegido in SENTIDOS:
            return elegido, "serie"
    manga = await asyncio.to_thread(_manga_del_archivo, Path(f.file_path))
    if manga == "YesAndRightToLeft":
        return "rtl", "comicinfo"
    tradicion = getattr(getattr(serie, "tradition", None), "value", None)
    if tradicion == "manga":
        return "rtl", "tradicion"
    return "ltr", "tradicion"


async def guardar_sentido(db: AsyncSession, file_id: UUID, sentido: str) -> None:
    if sentido not in SENTIDOS:
        raise LectorError("Ese sentido de lectura no existe.")
    f = await _abrir(db, file_id)
    issue = await db.get(Issue, f.issue_id)
    serie = await db.get(Series, issue.series_id) if issue is not None else None
    if serie is None:
        raise ArchivoNoLegibleError("Ese archivo no está vinculado a una serie.")
    serie.metadata_ = {**(serie.metadata_ or {}), "lector_sentido": sentido}
    await db.flush()
    await db.commit()


async def numero_de(db: AsyncSession, file_id: UUID) -> Issue | None:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        return None
    return await db.get(Issue, f.issue_id)


LEER = "leer"
FALTA = "falta"
SIN_SIGUIENTE = "sin_siguiente"


@dataclass(frozen=True)
class Siguiente:
    estado: str
    serie: Series | None = None
    numero: int | None = None
    issue: Issue | None = None
    archivo: ArchivoDeLectura | None = None


def _max_grapa(issues: list[Issue]) -> int | None:
    valores = [numero_de_grapa(getattr(i, "issue_number", None), getattr(i, "format", None))
               for i in issues]
    enteros = [v for v in valores if v is not None]
    return max(enteros) if enteros else None


async def siguiente_numero(db: AsyncSession, file_id: UUID) -> Siguiente:
    """Siguiente grapa de la serie de `file_id`, sin usar `sort_order`.

    Prioriza la grapa del número (o la mayor cubierta por un pack), comprueba
    posesión real y solo dice «te falta» cuando el total y los huecos son
    fiables. Requiere que el archivo exista y esté vinculado.
    """
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        return Siguiente(SIN_SIGUIENTE)
    actual = await db.get(Issue, f.issue_id)
    if actual is None:
        return Siguiente(SIN_SIGUIENTE)
    serie = await db.get(Series, actual.series_id)
    if serie is None:
        return Siguiente(SIN_SIGUIENTE)
    ids = list(f.covered_issue_ids or [])
    cubiertos = [actual]
    if ids:
        cubiertos = list((await db.execute(
            select(Issue).where(Issue.id.in_(ids))
        )).scalars().all()) or [actual]
    g = _max_grapa(cubiertos)
    if g is None:
        return Siguiente(SIN_SIGUIENTE, serie=serie)
    k = g + 1
    poseidos = await numeros_poseidos(db, serie.id)
    if k in poseidos:
        # `numeros_poseidos` normaliza «006» a 6: no se compara el texto crudo.
        candidatos = (await db.execute(
            select(Issue).where(
                Issue.series_id == serie.id,
                Issue.format == IssueFormat.SINGLE_ISSUE,
            ).order_by(Issue.id)
        )).scalars().all()
        issue = next((i for i in candidatos
                      if numero_de_grapa(i.issue_number, i.format) == k), None)
        archivo = await archivo_por_defecto(db, issue.id) if issue is not None else None
        if issue is not None and archivo is not None:
            return Siguiente(LEER, serie, k, issue, archivo)
        return Siguiente(SIN_SIGUIENTE, serie=serie)
    huecos = await huecos_de_serie(db, serie, poseidos=poseidos)
    if huecos.computable and k in huecos.faltantes:
        return Siguiente(FALTA, serie, k)
    return Siguiente(SIN_SIGUIENTE, serie=serie)


# ── OPDS-PSE (BL-LEC5, #828) ─────────────────────────────────────────────────────────────
#: Solo se anuncian páginas que un cliente OPDS lee tal cual: no se recodifica nada.
_PSE_CT = {"image/jpeg", "image/png", "image/gif"}
_PSE_EXTS = {ext for ext, ct in _CT.items() if ct in _PSE_CT}


@dataclass(frozen=True)
class Streaming:
    file_id: str
    count: int
    content_type: str
    ultima_leida: int | None


def pagina_pse_a_lector(numero_pse: int) -> int:
    """Página de OPDS-PSE (0 a N-1, especificación 1.0) → página del lector (1 a N)."""
    return numero_pse + 1


def ultima_leida_pse(current_page: int | None) -> int | None:
    """`pse:lastRead` a partir de `ReadingProgress.current_page`.

    Se envía la página en la que estás, 1-basada, tal cual (como hace Komga con su
    `readProgress.page`); `0` o ausente = sin empezar, y el atributo se omite. La
    especificación 1.0 no define `lastRead`: la base está sin probar con una app real.
    """
    if current_page is None or current_page < 1:
        return None
    return current_page


#: Medidas de ZIP ya hechas, por (ruta, mtime_ns, tamaño): un cambio del archivo la invalida.
#: Acotada para no crecer sin límite en una Pi de 512 MiB.
_MEDIDAS: dict[tuple[str, int, int], tuple[int, str] | None] = {}
_MEDIDAS_MAX = 4096
#: Medidas nuevas por petición del feed: abrir un ZIP en un disco USB frío cuesta, y una
#: serie de cientos de números no debe bloquear el feed. El resto se completa en las
#: siguientes peticiones (lo ya medido no cuenta).
MAX_MEDIDAS_NUEVAS = 150
_FALTA = object()


#: Marca de «no se pudo leer ahora»: un error de disco (USB ocupado) es pasajero y no se memoriza.
_TRANSITORIO = object()


def _medir_streaming(f: File) -> tuple[int, str] | None | object:
    """`(páginas, tipo)` si el archivo se puede servir YA y sin recodificar; si no, `None`.

    Devuelve `_TRANSITORIO` si falló por un error de disco, que puede no repetirse.
    """
    try:
        if es_rar_real(f):
            nombres = [p.name for p in CACHE._paginas(f)]
        else:
            nombres = [i.filename for i in _listado(Path(f.file_path))]
    except OSError:
        return _TRANSITORIO
    except LectorError as exc:
        return _TRANSITORIO if isinstance(exc.__cause__, OSError) else None
    if not nombres:
        return None
    exts = {Path(n).suffix.lower() for n in nombres}
    if not exts <= _PSE_EXTS:
        return None
    return len(nombres), _CT[Path(nombres[0]).suffix.lower()]


def _medir_todos(archivos: dict[UUID, File]) -> dict[UUID, tuple[int, str]]:
    medidos = {}
    nuevas = 0
    for issue_id, f in archivos.items():
        # Un RAR depende del estado de su caché de lectura (listar un directorio, barato):
        # no se memoriza. El ZIP sí, por ruta + fecha + tamaño.
        clave = None
        if not es_rar_real(f):
            try:
                st = Path(f.file_path).stat()
            except OSError:
                continue
            clave = (f.file_path, st.st_mtime_ns, st.st_size)
            previa = _MEDIDAS.get(clave, _FALTA)
            if previa is not _FALTA:
                if previa is not None:
                    medidos[issue_id] = previa
                continue
            if nuevas >= MAX_MEDIDAS_NUEVAS:
                continue
            nuevas += 1
        medida = _medir_streaming(f)
        if medida is _TRANSITORIO:
            continue
        if clave is not None:
            if len(_MEDIDAS) >= _MEDIDAS_MAX:
                _MEDIDAS.clear()
            _MEDIDAS[clave] = medida
        if medida is not None:
            medidos[issue_id] = medida
    return medidos


async def streaming_de_numeros(db: AsyncSession, issue_ids: list[UUID]) -> dict[UUID, Streaming]:
    """Qué números de una lista anuncian OPDS-PSE: uno por número, con el archivo por defecto.

    Un RAR solo cuenta si su caché de BL-LEC4 ya está lista (nunca se prepara desde aquí).
    """
    if not issue_ids:
        return {}
    filas = (await db.execute(
        select(File).where(File.issue_id.in_(issue_ids), File.is_missing.is_(False))
        .order_by(File.file_name)
    )).scalars().all()
    progresos = {p.issue_id: p for p in (await db.execute(
        select(ReadingProgress).where(ReadingProgress.issue_id.in_(issue_ids))
    )).scalars().all()}
    legibles: dict[UUID, list[File]] = {}
    for f in filas:
        if _es_legible(f):
            legibles.setdefault(f.issue_id, []).append(f)
    elegidos = {
        iid: _por_defecto(fs, getattr(progresos.get(iid), "file_id", None))
        for iid, fs in legibles.items()
    }
    medidos = await asyncio.to_thread(_medir_todos, elegidos)
    salida: dict[UUID, Streaming] = {}
    for iid, (cuenta, tipo) in medidos.items():
        progreso = progresos.get(iid)
        salida[iid] = Streaming(
            str(elegidos[iid].id), cuenta, tipo,
            ultima_leida_pse(progreso.current_page if progreso is not None else None))
    return salida


async def pagina_pse(db: AsyncSession, file_id: UUID, numero_pse: int) -> RecursoPagina:
    """Una página para un cliente OPDS-PSE: mismo servicio y mismos bytes que `/ui/leer`."""
    if numero_pse < 0:
        raise PaginaFueraDeRangoError("Esa página no existe.")
    recurso = await pagina(db, file_id, pagina_pse_a_lector(numero_pse))
    if recurso.content_type not in _PSE_CT:
        raise ArchivoNoLegibleError("Esa página no se puede servir sin recodificarla.")
    return recurso
