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
import os
import tempfile
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

import structlog
from fastapi import Request, Response
from PIL import Image

from zascarr.config import get_settings
from zascarr.core.formato_contenedor import (
    IMAGE_EXTS,
    MAX_PIXELES_PORTADA,
    EntradaNoLegible,
    clasificar_infos,
    firma_de,
    leer_acotado,
    natural_key,
    puede_dar_portada,
    se_lee_como_zip,
    zip_fuera_de_limite,
)
from zascarr.models import ClaseZip
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    CortesiaProceso,
    fuente_de_host_portada,
    fuente_habilitada,
)
from zascarr.utils.espacio import comprobar_espacio
from zascarr.utils.url_portada import (
    ESPERA_MAX_PORTADA_S,
    UrlNoPermitidaError,
    descargar_imagen,
    host_para_log,
)

logger = structlog.get_logger()

# Ancho de miniatura razonable para una tarjeta de revisión; no la portada
# a tamaño completo (esto se sirve muchas veces mientras la bandeja está
# abierta, y el dispositivo es una Pi).
_THUMB_MAX_WIDTH = 240

#: Ancho de la portada de serie (Biblioteca, Inicio y ficha). Medido en la especificación
#: BL-PORT1 (§9.2): 600 cubre 2,07× el peor caso presentado (290 CSS) sin `srcset`.
SERIES_COVER_MAX_WIDTH = 600

#: Versión de la clave de caché de la portada de serie: `covers/<CACHE_VERSION>/<id>.jpg`.
#: Un cambio de ancho objetivo o de algoritmo exige subir la versión (`v3`), porque la
#: ruta es lo que separa una caché vieja de una nueva (FR-03).
CACHE_VERSION = "v2"

#: Extensiones de las que `extract_cover_thumbnail` SABE sacar una miniatura (las que son un
#: zip). El resto (CBR, CB7, PDF, EPUB) no tiene extractor: «sin portada» se sabe por la
#: extensión, sin abrir el archivo. Esta constante y el extractor tienen que decir lo mismo,
#: por eso el extractor la usa.
EXTENSIONES_CON_PORTADA = frozenset({".cbz", ".zip"})


#: #435 (BL-PORT5): ancho mínimo, INCLUSIVO, de una portada previa para conservarla en vez de
#: sustituirla por la primera página del archivo. La antigua sacada de un CBZ mide ≤ 240 px y la de
#: una descarga ≤ 320 (`_THUMB_MAX_WIDTH`, `_COVER_MAX_WIDTH`), así que cualquier valor en (240,
#: 320] las separa. Es una constante del código, no un ajuste de usuario.
UMBRAL_PORTADA_PREVIA_PX = 300

#: Tope de bytes de una portada previa que se lee entera para medirla y servirla. Las hace ZascArr a
#: ≤ 320 px (decenas de KB); una mayor no es una de ellas y no se sube a memoria en la Pi.
MAX_BYTES_PORTADA_PREVIA = 8 * 1024 * 1024


@dataclass(frozen=True)
class PortadaPrevia:
    """Una portada previa suficiente: la ruta (para el `ETag` por `mtime`), los bytes ya leídos
    (los mismos que se miden y se sirven) y el ancho medido."""
    ruta: Path
    datos: bytes
    ancho: int


def rutas_de_portadas_previas(covers: Path, series_id: UUID | str) -> list[Path]:
    """LA lista ordenada de portadas previas de solo lectura de una serie (#435): se prueban por
    orden y se sirve la primera suficiente. Hoy solo la caché antigua `covers/<id>.jpg`; #418
    añadirá `covers/externa/<id>.jpg` aquí y en ningún otro sitio."""
    return [covers / f"{series_id}.jpg"]


def portada_previa_suficiente(covers: Path, series_id: UUID | str) -> PortadaPrevia | None:
    """La primera portada previa de la serie con ancho ≥ `UMBRAL_PORTADA_PREVIA_PX`, o `None`.

    ÚNICA regla de «portada previa suficiente» (compartida con #418). No abre archivos de la
    biblioteca, no usa la red y no escribe nada. El ancho sale de la CABECERA de la imagen (no se
    decodifica). Lo que no se puede leer, no es un JPEG o supera el tope de bytes NO cuenta como
    suficiente (falla cerrado): se sigue la cascada de siempre. El registro lleva el ancho y el
    umbral, o solo el tipo de error: nunca rutas."""
    for ruta in rutas_de_portadas_previas(covers, series_id):
        try:
            with open(ruta, "rb") as fh:
                datos = fh.read(MAX_BYTES_PORTADA_PREVIA + 1)
            if len(datos) > MAX_BYTES_PORTADA_PREVIA:
                continue
            with Image.open(io.BytesIO(datos)) as img:
                if img.format != "JPEG":
                    continue
                ancho = img.width
        except FileNotFoundError:
            continue
        except Exception as exc:   # OSError, imagen no válida, DecompressionBombError…
            logger.warning("cover.previa_ilegible", motivo=type(exc).__name__)
            continue
        if ancho >= UMBRAL_PORTADA_PREVIA_PX:
            logger.info("cover.previa_suficiente", ancho=ancho, umbral=UMBRAL_PORTADA_PREVIA_PX)
            return PortadaPrevia(ruta, datos, ancho)
    return None


def puede_tener_portada(ruta: str | Path, formato_contenido: dict | None = None) -> bool:
    """¿Tiene sentido pedir la portada de este archivo? Ni abre el archivo ni lo busca en disco
    (se llama en listados): decide con el
    `formato_contenido` ya guardado en la base (#307) y, si no hay nada guardado, solo por la
    extensión. `False` = ausencia CONOCIDA;
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


def es_candidato_de_portada(path: Path, formato_contenido: dict | None = None) -> bool:
    """¿Merece la pena abrir este archivo para sacar la portada de una serie (y gastar un intento)?

    Solo se descarta SIN leer el archivo la ausencia CONOCIDA (`puede_dar_portada(...) is False`: un
    `formato_contenido` guardado que dice que no es un ZIP legible). Lo desconocido (nada guardado o
    una lectura fallida antigua) se decide por la firma, 512 bytes como máximo: un `.cbr` que por
    dentro es ZIP se abre, uno que es RAR no. Así un RAR sin formato guardado no agota el tope de
    intentos antes de llegar a un CBZ, y un tebeo que hoy da portada sigue dándola (#419, criterio
    2)."""
    ext = path.suffix.lower()
    guardado = puede_dar_portada(ext, formato_contenido)
    if guardado is not None:
        return guardado
    return se_lee_como_zip(ext, firma_de(path))


def extract_cover_thumbnail(path: Path,
                            formato_contenido: dict | None = None,
                            *, ancho: int = _THUMB_MAX_WIDTH) -> tuple[bytes, str] | None:
    """(bytes JPEG, content-type) de una miniatura de la primera página en orden natural, o None
    si el archivo no es un ZIP legible, no
    tiene páginas de imagen o su primera página supera los topes (CBR real: requeriría una
    herramienta que no está; ver #308).

    `ancho` es el ancho máximo de la miniatura: 240 por defecto («Por revisar») y
    `SERIES_COVER_MAX_WIDTH` (600) para la portada de serie (BL-PORT1, #300). Se usa
    `Image.thumbnail`, que **nunca amplía**: un original menor se devuelve a su tamaño.

    #307: un `.cbr`/`.cb7` cuyo CONTENIDO es un ZIP se lee igual que un `.cbz`, siempre que sea un
    tebeo comprobado. Con el
    `formato_contenido` guardado en la base no se lee la firma; sin él (fila aún sin rellenar,
    fichero suelto) se decide aquí por el
    contenido. La lectura está ACOTADA: ni el tamaño declarado ni el ratio de la página pueden
    pasar de los topes."""
    if not path.exists():
        return None
    ext = path.suffix.lower()
    guardado = puede_dar_portada(ext, formato_contenido)
    # nada utilizable guardado (fila sin rellenar, fichero suelto, lectura fallida antigua)
    sin_guardar = guardado is None
    if sin_guardar:
        if not se_lee_como_zip(ext, firma_de(path)):
            return None
    elif not guardado:
        return None

    # declara demasiadas entradas o un directorio enorme: ni se abre
    if zip_fuera_de_limite(path):
        return None
    try:
        with zipfile.ZipFile(path) as zf:
            infos = zf.infolist()
            if (sin_guardar and ext not in (".cbz", ".zip")
                    and clasificar_infos(infos).clase is not ClaseZip.TEBEO):
                return None
            por_nombre = {i.filename: i for i in infos if not i.is_dir()}
            pages = sorted((n for n in por_nombre if Path(n).suffix.lower() in IMAGE_EXTS),
                           key=natural_key)
            if not pages:
                return None
            data = leer_acotado(zf, por_nombre[pages[0]])
    except (OSError, zipfile.BadZipFile, EntradaNoLegible):
        return None

    try:
        with Image.open(io.BytesIO(data)) as img:
            # `open` solo lee la cabecera: se rechaza SIN decodificar
            if img.width * img.height > MAX_PIXELES_PORTADA:
                return None
            img.thumbnail((ancho, ancho * 2))
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
        return Response(
            status_code=304, headers={"ETag": etag, "Cache-Control": "private, max-age=86400"}
        )
    return Response(
        content=data, media_type=content_type,
        headers={"ETag": etag, "Cache-Control": "private, max-age=86400"},
    )


async def fetch_and_cache_cover(url: str, dest: Path, *,
                                 ancho: int = _COVER_MAX_WIDTH,
                                 cortesia: CortesiaProceso | None = None,
                                 reloj=time.monotonic,
                                 dormir=asyncio.sleep,
                                 espera_max_s: float = ESPERA_MAX_PORTADA_S,
                                 resolutor=None, crear_cliente=None,
                                 motivo_fallo: list[str] | None = None) -> bool:
    """Descarga `url` (portada externa de Comic Vine/AniList/Tebeosfera/GCD), la redimensiona y
    la guarda en `dest`. Devuelve False sin lanzar si algo falla (URL no permitida, URL muerta,
    timeout, imagen ilegible): no se cachea nada en ese caso.

    `ancho` es el ancho máximo: 320 por defecto (Descubrir, FR-18) y
    `SERIES_COVER_MAX_WIDTH` (600) para la portada de serie (BL-PORT1, #300). Nunca amplía.

    ESTE es el punto común que hace la petición, y por eso la política de H1
    (`utils/url_portada.py`) se aplica AQUÍ y no solo donde se guarda la URL: protege también
    los registros ya almacenados y lo que devuelva una fuente. Destinos permitidos,
    direcciones resueltas, conexión a la dirección validada, redirecciones a mano (cada salto
    se valida), tamaño y tiempo máximos.

    Un semáforo global limita cuántas descargas corren a la vez, para no disparar una ráfaga
    de peticiones a un CDN externo cuando una rejilla entera de tarjetas carga en frío. El
    decode/resize de Pillow es síncrono y se manda a un hilo aparte.
    """
    ajustes = get_settings()
    # AC-12/AC-15: una fuente apagada no recibe portadas (se apaga en Ajustes, no en el .env).
    fuente = fuente_de_host_portada(host_para_log(url))
    if fuente is not None and not fuente_habilitada(fuente, ajustes):
        logger.info("cover.fuente_apagada", fuente=fuente)
        if motivo_fallo is not None:
            motivo_fallo.append("apagada")
        return False

    async with _COVER_FETCH_SEMAPHORE:
        try:
            content = await descargar_imagen(
                url, cortesia=cortesia, reloj=reloj, dormir=dormir,
                espera_max_s=espera_max_s, resolutor=resolutor,
                crear_cliente=crear_cliente, ajustes=ajustes)
        except CortesiaEnEspera as exc:
            # Espera visible sin prometer recuperación: no se envía y la ausencia no se cachea.
            logger.info("cover.cortesia_en_espera", motivo=exc.motivo,
                        espera_s=round(exc.espera_estimada_s, 1))
            if motivo_fallo is not None:
                motivo_fallo.append("cortesia")
            return False
        except UrlNoPermitidaError as exc:
            # Solo el host y el código: la URL entera puede llevar credenciales o claves.
            logger.warning("cover.url_rechazada", host=host_para_log(url), motivo=str(exc))
            return False
        except Exception:
            logger.warning("cover.fetch_failed", host=host_para_log(url))
            return False

    try:
        await asyncio.to_thread(_resize_and_save, content, dest, ancho)
        return True
    except Exception:
        logger.warning("cover.resize_failed", host=host_para_log(url))
        return False


def _resize_and_save(content: bytes, dest: Path, ancho: int = _COVER_MAX_WIDTH) -> None:
    with Image.open(io.BytesIO(content)) as img:
        img.thumbnail((ancho, ancho * 2))
        dest.parent.mkdir(parents=True, exist_ok=True)
        comprobar_espacio(dest.parent, len(content), "guardar la portada")
        _publicar_atomico(
            dest,
            lambda temporal: img.convert("RGB").save(temporal, format="JPEG", quality=85),
        )


#: Sufijo de los temporales propios; el mismo que usa `utils/cbz.py`.
_SUFIJO_TEMPORAL = ".zascarr.tmp"


def _publicar_atomico(dest: Path, escribir: Callable[[BinaryIO], None]) -> None:
    """Publica `dest` de una vez o no lo publica: el contenido se prepara en un temporal
    **único** creado con `tempfile.mkstemp` en el mismo directorio (nombre impredecible y
    `O_EXCL`: no se reutiliza ni se sigue un enlace plantado, y `os.replace` solo es atómico
    dentro del mismo sistema de ficheros) y se sustituye con `os.replace`. Si algo falla a
    mitad, el temporal se borra y `dest` conserva su versión anterior entera; una petición
    posterior puede reintentar. Sin esto, un corte dejaba un JPEG truncado que `exists()` da
    por bueno para siempre. Llamar dentro de `asyncio.to_thread`: es I/O de disco síncrono."""
    fd, ruta_temporal = tempfile.mkstemp(
        dir=dest.parent, prefix=f".{dest.name}.", suffix=_SUFIJO_TEMPORAL
    )
    try:
        with os.fdopen(fd, "wb") as temporal:
            escribir(temporal)
        os.replace(ruta_temporal, dest)
    finally:
        Path(ruta_temporal).unlink(missing_ok=True)


def write_cover_cache(dest: Path, data: bytes) -> None:
    """Guarda bytes ya listos (p.ej. de extract_cover_thumbnail, que ya
    redimensiona) directamente en la caché unificada de portadas — sin
    volver a pasar por Pillow. Llamar dentro de asyncio.to_thread: es
    I/O de disco síncrono."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    comprobar_espacio(dest.parent, len(data), "guardar la portada")
    _publicar_atomico(dest, lambda temporal: temporal.write(data))
