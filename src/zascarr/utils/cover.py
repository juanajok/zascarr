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

import structlog
from fastapi import Request, Response
from PIL import Image

from zascarr.core.formato_contenedor import (
    IMAGE_EXTS,
    EntradaNoLegible,
    clasificar_infos,
    firma_de,
    leer_acotado,
    natural_key,
    puede_dar_portada,
    se_lee_como_zip,
)
from zascarr.models import ClaseZip
from zascarr.utils.url_portada import UrlNoPermitidaError, descargar_imagen, host_para_log

logger = structlog.get_logger()

# Ancho de miniatura razonable para una tarjeta de revisión; no la portada
# a tamaño completo (esto se sirve muchas veces mientras la bandeja está
# abierta, y el dispositivo es una Pi).
_THUMB_MAX_WIDTH = 240

#: Extensiones de las que `extract_cover_thumbnail` SABE sacar una miniatura (las que son un
#: zip). El resto (CBR, CB7, PDF, EPUB) no tiene extractor: «sin portada» se sabe por la
#: extensión, sin abrir el archivo. Esta constante y el extractor tienen que decir lo mismo,
#: por eso el extractor la usa.
EXTENSIONES_CON_PORTADA = frozenset({".cbz", ".zip"})


def puede_tener_portada(ruta: str | Path, formato_contenido: dict | None = None) -> bool:
    """¿Tiene sentido pedir la portada de este archivo? Ni abre el archivo ni lo busca en disco (se llama en listados): decide con el
    `formato_contenido` ya guardado en la base (#307) y, si no hay nada guardado, solo por la extensión. `False` = ausencia CONOCIDA;
    `True` = disponibilidad desconocida (solo abriéndolo se sabe)."""
    ext = Path(str(ruta)).suffix.lower()
    guardado = puede_dar_portada(ext, formato_contenido)
    return guardado if guardado is not None else ext in EXTENSIONES_CON_PORTADA

# Portada de biblioteca: algo más grande que la miniatura de revisión de
# B2 (se ve en una tarjeta de la rejilla, no en una lista compacta).
_COVER_MAX_WIDTH = 320

# C1: no disparar N descargas concurrentes al CDN de Comic Vine/AniList
# si una rejilla entera de tarjetas carga en frío — mismo principio de
# cortesía que ya rige Tebeosfera/el scraper del foro.
_COVER_FETCH_SEMAPHORE = asyncio.Semaphore(2)


def extract_cover_thumbnail(path: Path, formato_contenido: dict | None = None) -> tuple[bytes, str] | None:
    """(bytes JPEG, content-type) de una miniatura de la primera página en orden natural, o None si el archivo no es un ZIP legible, no
    tiene páginas de imagen o su primera página supera los topes (CBR real: requeriría una herramienta que no está; ver #308).

    #307: un `.cbr`/`.cb7` cuyo CONTENIDO es un ZIP se lee igual que un `.cbz`, siempre que sea un tebeo comprobado. Con el
    `formato_contenido` guardado en la base no se lee la firma; sin él (fila aún sin rellenar, fichero suelto) se decide aquí por el
    contenido. La lectura está ACOTADA: ni el tamaño declarado ni el ratio de la página pueden pasar de los topes."""
    if not path.exists():
        return None
    ext = path.suffix.lower()
    sin_guardar = not formato_contenido
    if sin_guardar:
        if not se_lee_como_zip(ext, firma_de(path)):
            return None
    elif not puede_dar_portada(ext, formato_contenido):
        return None

    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if sin_guardar and ext not in (".cbz", ".zip") and clasificar_infos(infos).clase is not ClaseZip.TEBEO:
                return None
            por_nombre = {i.filename: i for i in infos if not i.is_dir()}
            pages = sorted((n for n in por_nombre if Path(n).suffix.lower() in IMAGE_EXTS), key=natural_key)
            if not pages:
                return None
            data = leer_acotado(zf, por_nombre[pages[0]])
    except (OSError, zipfile.BadZipFile, EntradaNoLegible):
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
    """Descarga `url` (portada externa de Comic Vine/AniList/Tebeosfera/GCD), la redimensiona y
    la guarda en `dest`. Devuelve False sin lanzar si algo falla (URL no permitida, URL muerta,
    timeout, imagen ilegible): no se cachea nada en ese caso.

    ESTE es el punto común que hace la petición, y por eso la política de H1
    (`utils/url_portada.py`) se aplica AQUÍ y no solo donde se guarda la URL: protege también
    los registros ya almacenados y lo que devuelva una fuente. Destinos permitidos,
    direcciones resueltas, conexión a la dirección validada, redirecciones a mano (cada salto
    se valida), tamaño y tiempo máximos.

    Un semáforo global limita cuántas descargas corren a la vez, para no disparar una ráfaga
    de peticiones a un CDN externo cuando una rejilla entera de tarjetas carga en frío. El
    decode/resize de Pillow es síncrono y se manda a un hilo aparte.
    """
    async with _COVER_FETCH_SEMAPHORE:
        try:
            content = await descargar_imagen(url)
        except UrlNoPermitidaError as exc:
            # Solo el host y el código: la URL entera puede llevar credenciales o claves.
            logger.warning("cover.url_rechazada", host=host_para_log(url), motivo=str(exc))
            return False
        except Exception:
            logger.warning("cover.fetch_failed", host=host_para_log(url))
            return False

    try:
        await asyncio.to_thread(_resize_and_save, content, dest)
        return True
    except Exception:
        logger.warning("cover.resize_failed", host=host_para_log(url))
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
