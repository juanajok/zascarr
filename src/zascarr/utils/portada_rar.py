# ruff: noqa: E501
"""
Portada de un tebeo RAR, leída de su propio archivo — #418 (BL-PORT3).

Une el lector de RAR (`utils/lector_rar`, que no sabe de portadas) con lo que es de portada: qué
candidato es un RAR, qué página se elige, cómo se recorta, y la marca por archivo que recuerda un
fallo para no reabrirlo mientras el archivo no cambie. Sin red y sin tocar el original.
"""
from __future__ import annotations

import io
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from PIL import Image

from zascarr.core.formato_contenedor import (
    EXT_CONTENEDOR,
    FRACCION_IMAGENES,
    IMAGE_EXTS,
    MAX_ENTRADA_LEIDA,
    MAX_PIXELES_PORTADA,
    MIN_IMAGENES,
    RUIDO,
    firma_de,
    natural_key,
)
from zascarr.models import Firma, MotivoRar
from zascarr.utils import lector_rar
from zascarr.utils.lector_rar import EntradaRar, ErrorRar, Listado

logger = structlog.get_logger()

#: Versión del contrato de la marca de fallo: si cambian los topes o la herramienta, subirla hace que
#: todos los archivos marcados se reintenten (FR-12).
CONTRATO_PORTADA_RAR = 1

#: Extensiones con firma RAR que se intentan: `.cbr` siempre; las otras solo si el listado lo
#: clasifica como tebeo (Q-8).
EXTENSIONES_RAR = frozenset({".cbr", ".rar", ""})

#: Motivos que son una propiedad DEL ARCHIVO y por eso se recuerdan (FR-10). Los del entorno
#: (herramienta ausente, error inesperado) se reintentan en la petición siguiente (FR-13).
MOTIVOS_DEL_ARCHIVO = frozenset({
    MotivoRar.CIFRADO, MotivoRar.MULTIVOLUMEN, MotivoRar.ILEGIBLE, MotivoRar.SIN_IMAGENES,
    MotivoRar.PAQUETE, MotivoRar.DEMASIADO_GRANDE, MotivoRar.TIEMPO,
})

#: El fallo por `tiempo` depende de la carga de la máquina, no del archivo: caduca y se reintenta
#: (dictamen SecOps B-3). Los demás motivos son del contenido y duran hasta que el archivo cambie.
CADUCIDAD_TIEMPO_S = 24 * 3600

_CARPETA_FALLOS = "fallos"
_CARPETA_TEMPORAL = ".rar-tmp"


def es_rar_candidato(path: Path, formato_contenido: dict | None = None) -> bool:
    """¿Es un RAR de verdad (por la firma, nunca por la extensión) y de una extensión que se intenta?
    Con el `formato_contenido` guardado no se lee el disco; sin él, 512 bytes como máximo."""
    if path.suffix.lower() not in EXTENSIONES_RAR:
        return False
    guardada = (formato_contenido or {}).get("firma")
    if guardada and guardada != Firma.ILEGIBLE.value:
        return guardada == Firma.RAR.value
    return firma_de(path) is Firma.RAR


# ── Elegir la página ─────────────────────────────────────────────────────────────────────────────
def _es_ruido_de_sistema(nombre: str) -> bool:
    partes = nombre.replace("\\", "/").split("/")
    return partes[0] == "__MACOSX" or partes[-1].startswith("._")


def elegir_pagina(listado: Listado, ext: str) -> EntradaRar:
    """La primera imagen en orden natural (la misma regla que el ZIP), sin `__MACOSX/` ni `._*`.

    Falla con `ErrorRar`: `SIN_IMAGENES` si no hay ninguna; `PAQUETE` si lleva dentro otros
    contenedores o, no siendo `.cbr`, no parece un solo tebeo (`MIN_IMAGENES` y `FRACCION_IMAGENES`)."""
    ficheros = [e for e in listado.entradas
                if not e.es_directorio and not _es_ruido_de_sistema(e.nombre)]
    paginas = sorted((e for e in ficheros if Path(e.nombre).suffix.lower() in IMAGE_EXTS),
                     key=lambda e: natural_key(e.nombre))
    if not paginas:
        raise ErrorRar(MotivoRar.SIN_IMAGENES)
    if any(Path(e.nombre).suffix.lower() in EXT_CONTENEDOR for e in ficheros):
        raise ErrorRar(MotivoRar.PAQUETE)
    if ext != ".cbr":
        contenido = [e for e in ficheros if Path(e.nombre).name.lower() not in RUIDO]
        if len(paginas) < MIN_IMAGENES or len(paginas) / max(len(contenido), 1) < FRACCION_IMAGENES:
            raise ErrorRar(MotivoRar.PAQUETE)
    return paginas[0]


def _jpeg_de(datos: bytes, ancho: int, max_pixeles: int | None = None) -> tuple[bytes, str]:
    """Recorta a `ancho` SIN ampliar y devuelve JPEG calidad 80, como el ZIP. La cabecera se mide antes
    de decodificar: una imagen enorme no se carga."""
    try:
        with Image.open(io.BytesIO(datos)) as img:
            if img.width * img.height > (max_pixeles or MAX_PIXELES_PORTADA):
                raise ErrorRar(MotivoRar.DEMASIADO_GRANDE)
            img.thumbnail((ancho, ancho * 2))
            salida = io.BytesIO()
            img.convert("RGB").save(salida, format="JPEG", quality=80)
            return salida.getvalue(), "image/jpeg"
    except ErrorRar:
        raise
    except Exception as exc:      # Pillow no pudo decodificar: archivo, no entorno
        raise ErrorRar(MotivoRar.ILEGIBLE) from exc


def portada_de_rar(path: Path, covers: Path, *, ancho: int,
                   max_pixeles: int | None = None) -> tuple[bytes, str]:
    """(JPEG, content-type) de la primera página de un RAR. Falla con `ErrorRar`; el temporal se
    crea dentro de `covers` y se borra siempre."""
    # un solo turno para listar y leer: no se pierde a mitad bajo carga (dictamen SecOps N-2 b)
    with lector_rar.turno(), lector_rar.carpeta_temporal(covers / _CARPETA_TEMPORAL) as tmp:
        listado = lector_rar.listar(path, temporal=tmp)
        pagina = elegir_pagina(listado, path.suffix.lower())
        datos = lector_rar.leer_entrada(path, pagina, MAX_ENTRADA_LEIDA, temporal=tmp)
    return _jpeg_de(datos, ancho, max_pixeles=max_pixeles)


# ── Marca de fallo por archivo ───────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Huella:
    tamano: int
    mtime_ns: int


def _huella_de(path: Path) -> Huella | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return Huella(st.st_size, st.st_mtime_ns)


def ruta_de_marca(carpeta_cache: Path, file_id: UUID) -> Path:
    return carpeta_cache / _CARPETA_FALLOS / f"{file_id}.json"


def marca_vigente(carpeta_cache: Path, file_id: UUID, path: Path) -> bool:
    """¿Hay una marca de fallo de este archivo que siga valiendo? Vale si el contrato, el tamaño y el
    `mtime_ns` coinciden con los de ahora. Una marca ilegible no vale (se reintenta)."""
    huella = _huella_de(path)
    if huella is None:
        return False
    try:
        marca = json.loads(ruta_de_marca(carpeta_cache, file_id).read_text())
        if not (marca["v"] == CONTRATO_PORTADA_RAR and marca["tamano"] == huella.tamano
                and marca["mtime_ns"] == huella.mtime_ns):
            return False
        if marca["motivo"] == MotivoRar.TIEMPO.value:
            return 0 <= time.time() - float(marca["t"]) < CADUCIDAD_TIEMPO_S
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def escribir_marca(carpeta_cache: Path, file_id: UUID, path: Path, motivo: MotivoRar) -> None:
    """Recuerda el fallo: motivo, huella y contrato; sin ruta ni nombre (CLAUDE.md §5.4). Si no se
    puede escribir, se registra el tipo de error y la petición sigue (FR-14)."""
    huella = _huella_de(path)
    if huella is None:
        return
    destino = ruta_de_marca(carpeta_cache, file_id)
    marca = {"v": CONTRATO_PORTADA_RAR, "motivo": motivo.value,
             "tamano": huella.tamano, "mtime_ns": huella.mtime_ns}
    if motivo is MotivoRar.TIEMPO:
        marca["t"] = int(time.time())        # solo `tiempo` caduca (FR-29): la fecha no se guarda en las demás
    contenido = json.dumps(marca).encode()
    try:
        # import local: `cover` importa este módulo para decidir qué es candidato
        from zascarr.utils.cover import write_cover_cache
        write_cover_cache(destino, contenido)
    except OSError as exc:
        logger.warning("cover.marca_sin_escribir", motivo=type(exc).__name__,
                       errno=getattr(exc, "errno", None))


def barrer_temporales(covers: Path) -> int:
    """Borra los temporales de lectura que dejó un proceso muerto (OOM, `kill -9`) en
    `covers/.rar-tmp` (dictamen SecOps B-4). Se llama al arrancar, con un solo worker: ninguno está en
    uso. Devuelve cuántos borró; nunca lanza."""
    carpeta = covers / _CARPETA_TEMPORAL
    borrados = 0
    try:
        hijos = list(carpeta.iterdir())
    except OSError:
        return 0
    for hijo in hijos:
        shutil.rmtree(hijo, ignore_errors=True)
        borrados += 1
    return borrados
