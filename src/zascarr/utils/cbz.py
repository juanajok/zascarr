"""B6 — reescritura segura de un CBZ para (re)escribir su `ComicInfo.xml`.

Ficha `docs/design/benchmark-B6-comicinfo.md`. Nada de escribir sobre el
original in situ:

  1. (el llamante ya tiene el bloqueo por fichero tomado — ver el final);
  2. se calcula el **manifiesto de hashes** de las entradas no-XML del original;
  3. se comprueba el **espacio libre** (el temporal ocupa ~el tamaño original);
  4. se construye el CBZ nuevo en un temporal **único** creado con `mkstemp`
     (`O_EXCL`, mismo directorio ⇒ mismo sistema de ficheros);
  5. se **verifica**: ZIP íntegro, manifiesto idéntico y **exactamente una**
     entrada `ComicInfo.xml`;
  6. `fsync` del temporal, `os.replace` (atómico) y `fsync` del directorio
     (durabilidad ≠ atomicidad).

Un fallo en cualquier paso deja el **original intacto** y limpia el temporal.

Sobre el temporal: **nunca** se abre un nombre fijo con `ZipFile(..., "w")`,
porque eso trunca un fichero existente. `tempfile.mkstemp` lo crea de forma
exclusiva en el mismo directorio, así que un temporal de otra ejecución (o uno
que quedó de una anterior) no se pisa ni se reutiliza.

**Serialización: la pone quien llama, no este módulo.** Un `flock` sobre el
propio CBZ **no sirve**: el bloqueo va con el *inodo* y `os.replace` instala uno
nuevo, así que quien llegue después del reemplazo abre el inodo nuevo y entra sin
esperar al que todavía tiene el viejo (y encima podría borrarle el temporal). El
bloqueo tiene que tener una identidad que **sobreviva al reemplazo**; en ZascArr
es un *advisory lock* de PostgreSQL por `File.id`
(`services/tagger.py::bloqueo_de_fichero`). Este módulo no bloquea, y
`_limpiar_temporales_viejos` **exige** que el llamante lo tenga tomado.
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import structlog

from zascarr.core.comicinfo_write import ENTRADA_XML

logger = structlog.get_logger()

_CHUNK = 64 * 1024
#: Margen de seguridad sobre el tamaño del original (cabeceras del ZIP nuevo,
#: metadatos del sistema de ficheros).
MARGEN_BYTES = 1 * 1024 * 1024
#: Sufijo de los temporales propios (`.{nombre}.<aleatorio>.zascarr.tmp`).
SUFIJO_TMP = ".zascarr.tmp"


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


def _prefijo_temporal(path: Path) -> str:
    return f".{path.name}."


def _limpiar_temporales_viejos(path: Path) -> None:
    """Borra temporales propios que quedaran de una ejecución interrumpida.

    Solo es seguro hacerlo **con el bloqueo por fichero tomado** (el que pone
    `services/tagger.py::bloqueo_de_fichero`): en ese momento ningún otro
    etiquetado puede estar escribiendo este CBZ, así que cualquier temporal con
    su prefijo es basura. Sin esto, un `mkstemp` único por ejecución dejaría los
    restos de un `kill -9` para siempre."""
    prefijo, sufijo = _prefijo_temporal(path), SUFIJO_TMP
    try:
        with os.scandir(path.parent) as entradas:
            for entrada in entradas:
                if entrada.name.startswith(prefijo) and entrada.name.endswith(sufijo):
                    with contextlib.suppress(OSError):
                        os.unlink(entrada.path)
    except OSError:
        logger.warning("cbz.limpieza_temporales_fallida", dir=str(path.parent))


# ── lectura ─────────────────────────────────────────────────────────────────

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


# ── escritura ───────────────────────────────────────────────────────────────

def reescribir_con_xml(path: Path, xml: bytes) -> None:
    """Sustituye el CBZ por uno idéntico con `ComicInfo.xml` (una sola entrada,
    en la raíz). Lanza `CbzError` sin tocar el original si algo no cuadra.

    **No toma ningún bloqueo**: quien llama tiene que haber serializado la
    secuencia leer → plan → reemplazar (ver el docstring del módulo) y mantenerla
    hasta que esto vuelva. Sin eso, dos etiquetados del mismo tebeo pueden
    reconstruir la misma ruta a la vez."""
    path = Path(path)
    try:
        _reescribir(path, xml)
    except OSError as exc:  # no existe, sin permiso, disco desconectado…
        raise CbzInvalidoError(f"CBZ ilegible: {exc}") from exc


def _reescribir(path: Path, xml: bytes) -> None:
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

    _limpiar_temporales_viejos(path)

    # mkstemp crea el fichero con O_EXCL: nombre único y sin truncar nada.
    fd, nombre_temporal = tempfile.mkstemp(
        dir=str(path.parent), prefix=_prefijo_temporal(path), suffix=SUFIJO_TMP,
    )
    temporal = Path(nombre_temporal)
    try:
        with os.fdopen(fd, "wb") as fh, \
                zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zout, \
                zipfile.ZipFile(path) as zin:
            for info in zin.infolist():
                if info.is_dir() or _es_comicinfo(info.filename):
                    continue
                with zin.open(info) as src, zout.open(info, "w") as dst:
                    shutil.copyfileobj(src, dst, _CHUNK)
            zout.writestr(ENTRADA_XML, xml)

        _verificar(temporal, manifiesto_original)

        # Durabilidad: el contenido del temporal a disco ANTES de renombrarlo.
        dfd = os.open(temporal, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)

        os.replace(temporal, path)

        # Persistir el renombrado (si el sistema de ficheros lo permite).
        try:
            pfd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(pfd)
            finally:
                os.close(pfd)
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
