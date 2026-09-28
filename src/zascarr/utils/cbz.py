"""B6 — reescritura segura de un CBZ para (re)escribir su `ComicInfo.xml`.

Ficha `docs/design/benchmark-B6-comicinfo.md`. Nada de escribir sobre el
original in situ:

  1. se calcula el **manifiesto de hashes** de las entradas no-XML del original;
  2. se comprueba el **espacio libre** (el temporal ocupa ~el tamaño original);
  3. se construye el CBZ nuevo en un temporal **del mismo directorio**;
  4. se **verifica**: ZIP íntegro, manifiesto idéntico y **exactamente una**
     entrada `ComicInfo.xml`;
  5. `fsync` del temporal, `os.replace` (atómico) y `fsync` del directorio
     (durabilidad ≠ atomicidad).

Un fallo en cualquier paso deja el **original intacto** y limpia el temporal.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import zipfile
from pathlib import Path

import structlog

from zascarr.core.comicinfo_write import ENTRADA_XML

logger = structlog.get_logger()

_CHUNK = 64 * 1024
#: Margen de seguridad sobre el tamaño del original (cabeceras del ZIP nuevo,
#: metadatos del sistema de ficheros).
MARGEN_BYTES = 1 * 1024 * 1024


class CbzError(Exception):
    """Base de los fallos de reescritura (el original queda intacto)."""


class CbzInvalidoError(CbzError):
    pass


class SinEspacioError(CbzError):
    pass


class VerificacionError(CbzError):
    pass


def _es_comicinfo(nombre: str) -> bool:
    return os.path.basename(nombre).lower() == ENTRADA_XML.lower()


def leer_comicinfo(path: Path) -> bytes | None:
    """Bytes del primer `ComicInfo.xml` del CBZ (case-insensitive), o None."""
    with zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            if not info.is_dir() and _es_comicinfo(info.filename):
                return zf.read(info)
    return None


def _manifiesto(zf: zipfile.ZipFile) -> dict[str, str]:
    """nombre → SHA256 del contenido, para las entradas NO-XML (por streaming)."""
    out: dict[str, str] = {}
    for info in zf.infolist():
        if info.is_dir() or _es_comicinfo(info.filename):
            continue
        h = hashlib.sha256()
        with zf.open(info) as f:
            for chunk in iter(lambda: f.read(_CHUNK), b""):
                h.update(chunk)
        out[info.filename] = h.hexdigest()
    return out


def reescribir_con_xml(path: Path, xml: bytes) -> None:
    """Sustituye el CBZ por uno idéntico con `ComicInfo.xml` (una sola entrada,
    en la raíz). Lanza `CbzError` sin tocar el original si algo no cuadra."""
    path = Path(path)
    try:
        with zipfile.ZipFile(path) as zf:
            manifiesto_original = _manifiesto(zf)
    except (OSError, zipfile.BadZipFile) as exc:
        raise CbzInvalidoError(f"CBZ ilegible: {exc}") from exc

    original_size = path.stat().st_size
    libre = shutil.disk_usage(path.parent).free
    if libre < original_size + MARGEN_BYTES:
        raise SinEspacioError(
            f"espacio insuficiente: {libre} libres, hacen falta "
            f"~{original_size + MARGEN_BYTES}"
        )

    temporal = path.with_name(f".{path.name}.zascarr.tmp")
    try:
        with zipfile.ZipFile(path) as zin, \
                zipfile.ZipFile(temporal, "w", zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                if info.is_dir() or _es_comicinfo(info.filename):
                    continue
                with zin.open(info) as src, zout.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, _CHUNK)
            zout.writestr(ENTRADA_XML, xml)

        _verificar(temporal, manifiesto_original)

        # Durabilidad: el contenido del temporal a disco ANTES de renombrarlo.
        fd = os.open(temporal, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

        os.replace(temporal, path)

        # Persistir el renombrado (si el sistema de ficheros lo permite).
        try:
            dfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError:
            logger.warning("cbz.fsync_dir_fallido", dir=str(path.parent))
    except CbzError:
        _limpiar(temporal)
        raise
    except Exception as exc:  # noqa: BLE001 — cualquier fallo limpia el temporal
        _limpiar(temporal)
        raise CbzError(f"reescritura fallida: {exc}") from exc


def _verificar(temporal: Path, manifiesto_original: dict[str, str]) -> None:
    try:
        with zipfile.ZipFile(temporal) as zf:
            if zf.testzip() is not None:  # CRC/cabeceras del ZIP NUEVO
                raise VerificacionError("CRC inválido en el CBZ reconstruido")
            if _manifiesto(zf) != manifiesto_original:
                raise VerificacionError(
                    "las entradas no-XML no coinciden con el original"
                )
            nombres = [
                os.path.basename(i.filename).lower()
                for i in zf.infolist() if not i.is_dir()
            ]
            if nombres.count(ENTRADA_XML.lower()) != 1:
                raise VerificacionError("no hay exactamente una ComicInfo.xml")
    except zipfile.BadZipFile as exc:
        raise VerificacionError(f"CBZ reconstruido ilegible: {exc}") from exc


def _limpiar(temporal: Path) -> None:
    try:
        temporal.unlink(missing_ok=True)
    except OSError:
        logger.warning("cbz.temporal_no_borrado", path=str(temporal))
