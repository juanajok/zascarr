"""Portada de colección: mosaico 2:3 de portadas YA cacheadas + override.

Sin red, sin extraer CBZ y sin subida. El mosaico se compone en servidor con
Pillow a 600×900 y se cachea en `covers/colecciones/<collection_id>.jpg` con
un sidecar de huella. La elección de una serie miembro (`cover_series_id`) gana
al mosaico; si deja de ser miembro o no tiene portada, se cae al mosaico.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from PIL import Image, ImageOps
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import Collection, Series
from zascarr.utils.cover import (
    CACHE_VERSION,
    CARPETA_EXTERNA,
    MAX_BYTES_PORTADA_PREVIA,
    write_cover_cache,
)

logger = structlog.get_logger()

ANCHO = 600
ALTO = 900
CARPETA = "colecciones"
MAXIMO = 4
VERSION = 1
#: Límites defensivos al componer: un JPEG de portada real mide pocos cientos de KB y
#: 600×900; no se decodifica nada mayor ni se sigue un symlink dentro de `covers/`.
MAX_BYTES = MAX_BYTES_PORTADA_PREVIA
MAX_PIXELES = 4_000_000
#: Fondo neutro de las celdas vacías del mosaico (no es una imagen de nadie).
FONDO = (232, 226, 214)

_LOCKS: dict[str, asyncio.Lock] = {}


@dataclass(frozen=True)
class CandidataPortada:
    series_id: str
    title: str
    tiene_portada: bool


@dataclass
class ResultadoPortada:
    datos: bytes
    content_type: str = "image/jpeg"
    etag: str = ""
    cacheable: bool = True


@dataclass(frozen=True)
class ResultadoEleccion:
    ok: bool
    errores: dict[str, str]


def _covers() -> Path:
    return Path(get_settings().covers_cache_path)


def ruta_cache(collection_id: UUID | str) -> Path:
    return _covers() / CARPETA / f"{collection_id}.jpg"


def ruta_sidecar(collection_id: UUID | str) -> Path:
    return _covers() / CARPETA / f"{collection_id}.json"


def _ruta_de_cache_valida(covers: Path, ruta: Path) -> bool:
    try:
        if ruta.is_symlink() or not ruta.is_file():
            return False
        raiz = covers.resolve()
        return ruta.resolve().is_relative_to(raiz)
    except OSError:
        return False


def portada_cacheada(covers: Path, series_id: UUID | str) -> Path | None:
    """Primera portada de serie ya cacheada, en el orden v3 → externa → legado.

    No sigue symlinks ni sale de `covers/`; una ruta así no cuenta como portada.
    """
    for ruta in (
        covers / CACHE_VERSION / f"{series_id}.jpg",
        covers / CARPETA_EXTERNA / f"{series_id}.jpg",
        covers / f"{series_id}.jpg",
    ):
        if _ruta_de_cache_valida(covers, ruta):
            return ruta
    return None


def _leer_jpeg(path: Path) -> bytes | None:
    try:
        with path.open("rb") as fh:
            datos = fh.read(MAX_BYTES + 1)
        if len(datos) > MAX_BYTES:
            return None
        with Image.open(io.BytesIO(datos)) as img:
            if img.format != "JPEG":
                return None
            if img.width <= 0 or img.height <= 0 or img.width * img.height > MAX_PIXELES:
                return None
        return datos
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _celda(img: Image.Image, ancho: int, alto: int) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), (ancho, alto), method=Image.Resampling.LANCZOS)


def componer_mosaico(rutas: list[Path]) -> bytes:
    """Compone 1–4 portadas en 600×900. Sin texto ni red."""
    lienzo = Image.new("RGB", (ANCHO, ALTO), FONDO)
    imagenes: list[Image.Image] = []
    for ruta in rutas[:MAXIMO]:
        try:
            datos = _leer_jpeg(ruta)
            if datos is None:
                continue
            with Image.open(io.BytesIO(datos)) as img:
                img.load()
                imagenes.append(img.convert("RGB").copy())
        except (OSError, ValueError, Image.DecompressionBombError):
            continue
    if not imagenes:
        raise ValueError("sin portadas")
    if len(imagenes) == 1:
        lienzo.paste(_celda(imagenes[0], ANCHO, ALTO), (0, 0))
    elif len(imagenes) == 2:
        for i, img in enumerate(imagenes):
            lienzo.paste(_celda(img, ANCHO // 2, ALTO), (i * (ANCHO // 2), 0))
    else:
        for i, img in enumerate(imagenes[:4]):
            x = (i % 2) * (ANCHO // 2)
            y = (i // 2) * (ALTO // 2)
            lienzo.paste(_celda(img, ANCHO // 2, ALTO // 2), (x, y))
    buf = io.BytesIO()
    lienzo.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


async def candidatas_portada(db: AsyncSession, collection_id: UUID) -> list[CandidataPortada]:
    filas = (await db.execute(
        select(Series).where(Series.collection_id == collection_id)
        .order_by(Series.sort_title, Series.title, Series.id)
    )).scalars().all()
    covers = _covers()
    return [CandidataPortada(str(s.id), s.title,
                             portada_cacheada(covers, s.id) is not None)
            for s in filas]


async def _miembros(db: AsyncSession, collection_id: UUID) -> list[Series]:
    return list((await db.execute(
        select(Series).where(Series.collection_id == collection_id)
        .order_by(Series.sort_title, Series.title, Series.id)
    )).scalars().all())


def _huella(miembros: list[Series], covers: Path) -> list[dict]:
    huella = []
    for serie in miembros:
        ruta = portada_cacheada(covers, serie.id)
        item = {"series_id": str(serie.id), "path": str(ruta) if ruta else None}
        if ruta is not None:
            try:
                st = ruta.stat()
                item.update(mtime_ns=st.st_mtime_ns, size=st.st_size)
            except OSError:
                item.update(mtime_ns=None, size=None)
        huella.append(item)
    return huella


def _etag_de(path: Path) -> str:
    st = path.stat()
    return f'"{st.st_mtime_ns}-{st.st_size}"'


def _etag_bytes(datos: bytes) -> str:
    return '"' + hashlib.sha256(datos).hexdigest()[:32] + '"'


async def obtener_portada(db: AsyncSession, collection_id: UUID) -> ResultadoPortada | None:
    coleccion = await db.get(Collection, collection_id)
    if coleccion is None:
        return None
    covers = _covers()
    # Override: solo si sigue siendo miembro y su portada está cacheada.
    if coleccion.cover_series_id is not None:
        miembro = (await db.execute(
            select(Series).where(Series.id == coleccion.cover_series_id,
                                 Series.collection_id == collection_id))).scalar_one_or_none()
        ruta = portada_cacheada(covers, coleccion.cover_series_id) if miembro else None
        if ruta is not None:
            datos = await asyncio.to_thread(_leer_jpeg, ruta)
            if datos is not None:
                return ResultadoPortada(datos, etag=await asyncio.to_thread(_etag_de, ruta))
    miembros = await _miembros(db, collection_id)
    huella = await asyncio.to_thread(_huella, miembros, covers)
    rutas = [Path(item["path"]) for item in huella
             if item["path"] and item.get("mtime_ns") is not None][:MAXIMO]
    if not rutas:
        return None
    jpg = ruta_cache(collection_id)
    sidecar = ruta_sidecar(collection_id)
    lock = _LOCKS.setdefault(str(collection_id), asyncio.Lock())
    async with lock:
        if jpg.is_file() and sidecar.is_file():
            try:
                previo = json.loads(await asyncio.to_thread(sidecar.read_text, encoding="utf-8"))
                if previo.get("version") == VERSION and previo.get("huella") == huella:
                    datos = await asyncio.to_thread(_leer_jpeg, jpg)
                    if datos is not None:
                        return ResultadoPortada(datos, etag=await asyncio.to_thread(_etag_de, jpg))
            except (OSError, ValueError):
                pass
        try:
            datos = await asyncio.to_thread(componer_mosaico, rutas)
        except (OSError, ValueError) as exc:
            logger.warning("portada_coleccion.componer_falló", collection_id=str(collection_id),
                           motivo=type(exc).__name__)
            return None
        cacheable = True
        try:
            def _escribir() -> None:
                write_cover_cache(jpg, datos)
                write_cover_cache(sidecar, json.dumps(
                    {"version": VERSION, "huella": huella,
                     "generado_en": int(time.time())}, ensure_ascii=False).encode("utf-8"))
            await asyncio.to_thread(_escribir)
        except Exception:
            cacheable = False
            logger.warning("portada_coleccion.cache_falló", collection_id=str(collection_id))
        etag = await asyncio.to_thread(_etag_de, jpg) if cacheable else _etag_bytes(datos)
        return ResultadoPortada(datos, etag=etag, cacheable=cacheable)


async def elegir_portada(db: AsyncSession, collection_id: UUID,
                         series_id: UUID | None) -> ResultadoEleccion:
    coleccion = await db.get(Collection, collection_id)
    if coleccion is None:
        return ResultadoEleccion(False, {"general": "La colección ya no existe."})
    if series_id is None:
        coleccion.cover_series_id = None
        await db.flush()
        return ResultadoEleccion(True, {})
    serie = await db.get(Series, series_id)
    if serie is None or serie.collection_id != collection_id:
        return ResultadoEleccion(False, {
            "portada": "Esa serie no pertenece a la colección; elige una de sus series."})
    coleccion.cover_series_id = series_id
    await db.flush()
    return ResultadoEleccion(True, {})


async def borrar_cache(collection_id: UUID | str) -> None:
    """Best-effort al borrar la colección; nunca falla el borrado.

    Bajo el mismo lock que la composición: no se borra mientras otra petición
    está escribiendo el mosaico (ni al revés).
    """
    lock = _LOCKS.setdefault(str(collection_id), asyncio.Lock())
    async with lock:
        for ruta in (ruta_cache(collection_id), ruta_sidecar(collection_id)):
            try:
                await asyncio.to_thread(ruta.unlink, missing_ok=True)
            except OSError:
                logger.warning("portada_coleccion.borrar_cache_falló")
