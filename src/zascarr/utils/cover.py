"""
Extracción de portada bajo demanda — B2 (miniaturas en la bandeja de
pendientes) y C1 (portadas de la biblioteca, con caché unificada en
disco). No reutiliza triage(): esta solo necesita los bytes de la
primera página redimensionados para una miniatura, no todo el triaje
(SHA256, ComicInfo.xml, etc.), que ya se hizo una vez al importar.
"""
from __future__ import annotations

import asyncio
import io
import zipfile
from pathlib import Path

import httpx
import structlog
from fastapi import Request, Response
from PIL import Image

from zascarr.core.importer_triage import IMAGE_EXTS, natural_key

logger = structlog.get_logger()

# Ancho de miniatura razonable para una tarjeta de revisión; no la portada
# a tamaño completo (esto se sirve muchas veces mientras la bandeja está
# abierta, y el dispositivo es una Pi).
_THUMB_MAX_WIDTH = 240

# Portada de biblioteca: algo más grande que la miniatura de revisión de
# B2 (se ve en una tarjeta de la rejilla, no en una lista compacta).
_COVER_MAX_WIDTH = 320

# C1: no disparar N descargas concurrentes al CDN de Comic Vine/AniList
# si una rejilla entera de tarjetas carga en frío — mismo principio de
# cortesía que ya rige Tebeosfera/el scraper del foro.
_COVER_FETCH_SEMAPHORE = asyncio.Semaphore(2)


def extract_cover_thumbnail(path: Path) -> tuple[bytes, str] | None:
    """(bytes JPEG, content-type) de una miniatura de la primera página en
    orden natural, o None si el archivo no es un zip legible o no tiene
    páginas de imagen (CBR, por ejemplo: requeriría unrar, fuera de
    alcance — ver importer_triage.py)."""
    if path.suffix.lower() not in {".cbz", ".zip"} or not path.exists():
        return None

    try:
        with zipfile.ZipFile(path) as zf:
            pages = sorted(
                (n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS),
                key=natural_key,
            )
            if not pages:
                return None
            data = zf.read(pages[0])
    except (OSError, zipfile.BadZipFile):
        return None

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.thumbnail((_THUMB_MAX_WIDTH, _THUMB_MAX_WIDTH * 2))
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=80)
            return buf.getvalue(), "image/jpeg"
    except Exception:
        # Pillow no pudo decodificar la imagen: mejor sin miniatura que
        # un error que tumbe la carga de toda la bandeja.
        return None


def cached_image_response(request: Request, data: bytes, content_type: str, etag: str) -> Response:
    """Cabeceras HTTP de caché para una imagen ya resuelta (C1, cierra
    también M4 del peer review: el endpoint de miniaturas de B2 nació
    sin ellas). 304 si el cliente ya tiene esta versión (If-None-Match),
    si no 200 con Cache-Control privado — son portadas de una biblioteca
    personal, no contenido público cacheable por un proxy intermedio."""
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=86400"})
    return Response(
        content=data, media_type=content_type,
        headers={"ETag": etag, "Cache-Control": "private, max-age=86400"},
    )


async def fetch_and_cache_cover(url: str, dest: Path) -> bool:
    """Descarga `url` (portada externa de Comic Vine/AniList/Tebeosfera),
    la redimensiona y la guarda en `dest`. Devuelve False sin lanzar si
    algo falla (URL muerta, timeout, imagen ilegible) — no se cachea
    nada en ese caso, la próxima petición simplemente reintenta.

    La descarga usa un cliente async (no bloquea el loop por sí sola) y
    un semáforo global limita cuántas descargas de portada corren a la
    vez, para no disparar una ráfaga de peticiones a un CDN externo
    cuando una rejilla entera de tarjetas carga en frío. El decode/
    resize de Pillow sí es síncrono y se manda a un hilo aparte.
    """
    async with _COVER_FETCH_SEMAPHORE:
        try:
            # follow_redirects: los CDN de portadas externas (Comic Vine,
            # AniList, y el propio picsum.photos usado para verificar esto
            # en vivo) redirigen con 302 con normalidad — sin esto,
            # raise_for_status() lo trata como fallo y nunca se llega a
            # descargar ninguna imagen real. Encontrado probando en vivo,
            # no algo que un mock hubiera revelado.
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                r = await client.get(url)
                r.raise_for_status()
                content = r.content
        except Exception:
            logger.warning("cover.fetch_failed", url=url[:200])
            return False

    try:
        await asyncio.to_thread(_resize_and_save, content, dest)
        return True
    except Exception:
        logger.warning("cover.resize_failed", url=url[:200])
        return False


def _resize_and_save(content: bytes, dest: Path) -> None:
    with Image.open(io.BytesIO(content)) as img:
        img.thumbnail((_COVER_MAX_WIDTH, _COVER_MAX_WIDTH * 2))
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.convert("RGB").save(dest, format="JPEG", quality=85)


def write_cover_cache(dest: Path, data: bytes) -> None:
    """Guarda bytes ya listos (p.ej. de extract_cover_thumbnail, que ya
    redimensiona) directamente en la caché unificada de portadas — sin
    volver a pasar por Pillow. Llamar dentro de asyncio.to_thread: es
    I/O de disco síncrono."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
