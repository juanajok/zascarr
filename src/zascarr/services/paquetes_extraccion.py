"""#344 BL-PACK1 corte 3: extracción y verificación durable de paquetes.

Solo escribe en un temporal propio bajo `covers_cache_path/.paquetes`; nunca publica,
importa ni toca la biblioteca/Descargas. El original permanece intacto.
Termina en `verificado` (corte 4 publica).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import zipfile
import zipfile as _zip
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.formato_contenedor import (
    MAX_ENTRADA_LEIDA,
    MAX_PIXELES_PORTADA,
    Firma,
    firma_de_bytes,
)
from zascarr.models import PaqueteEstado, PaqueteOperacion
from zascarr.services.paquetes import (
    MAX_BYTES_ENTRADA,
    MAX_BYTES_TOTAL,
    MAX_RATIO_LEIDA,
    ListadoPaquete,
    PaqueteError,
    PaquetePendiente,
    listar_paquete,
)
from zascarr.utils import lector_rar
from zascarr.utils.espacio import comprobar_espacio

_ZIP_TIMEOUT = 120

_EXTS_IMAGEN = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}

logger = structlog.get_logger()

_BLOQUE = 1024 * 1024


class PaqueteExtraccionError(Exception):
    """Causa sancionada de extracción/verificación; nunca lleva rutas."""

    def __init__(self, codigo: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


@dataclass(frozen=True)
class ResultadoExtraccion:
    operacion_id: UUID
    items: tuple[dict, ...]
    total_bytes: int


def clave_identidad(p: PaquetePendiente) -> str:
    crudo = "|".join(str(x) for x in (p.ruta, p.dev, p.ino, p.tamano, p.mtime_ns, p.firma))
    return hashlib.sha256(crudo.encode("utf-8", "surrogateescape")).hexdigest()


def _base_temporal() -> Path:
    ajustes = get_settings()
    base = Path(ajustes.covers_cache_path) / ".paquetes"
    prohibidas: list[Path] = []
    for valor in (getattr(ajustes, "library_path", None),
                  getattr(ajustes, "transmission_download_dir", None),
                  getattr(ajustes, "amule_incoming_dir", None),
                  getattr(ajustes, "downloads_path", None)):
        if valor:
            prohibidas.append(Path(valor).resolve(strict=False))
    padre = base.parent.resolve(strict=False)
    for prohibida in prohibidas:
        if padre == prohibida or prohibida in padre.parents:
            raise PaqueteExtraccionError(
                "temporal_inseguro", "El temporal está dentro de una carpeta vigilada.")
    if not base.exists():
        base.mkdir(parents=True, mode=0o700, exist_ok=True)
    try:
        fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except OSError as exc:
        raise PaqueteExtraccionError(
            "temporal_inseguro", "La carpeta temporal no es segura.") from exc
    try:
        real = Path(os.path.realpath(f"/proc/self/fd/{fd}"))
        if real != base:
            raise PaqueteExtraccionError(
                "temporal_inseguro", "La carpeta temporal cambió.")
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)
    return real


def _crear_temp(base: Path, prefijo: str) -> tuple[Path, int]:
    """Crea la subcarpeta con dir_fd verificado y devuelve (ruta, fd abierto)."""
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        real = Path(os.path.realpath(f"/proc/self/fd/{fd}"))
        if real != base:
            raise PaqueteExtraccionError("temporal_inseguro", "La carpeta temporal cambió.")
        nombre = f"{prefijo}-{os.urandom(6).hex()}"
        os.mkdir(nombre, 0o700, dir_fd=fd)
        try:
            hijo = os.open(nombre, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                           dir_fd=fd)
        except BaseException:
            with __import__("contextlib").suppress(OSError):
                os.rmdir(nombre, dir_fd=fd)
            raise
    finally:
        os.close(fd)
    return base / nombre, hijo


def _borrar_temp(ruta: Path) -> bool:
    try:
        shutil.rmtree(ruta)
        return True
    except OSError:
        logger.warning("paquetes.temporal_sin_borrar", error="limpieza")
        return False


def _nombre_generado(indice: int, tipo: str) -> str:
    return f"{indice + 1:04d}.{tipo.lower()}"


def _comprobar_original(p: PaquetePendiente) -> None:
    try:
        st = p.ruta.stat(follow_symlinks=False)
    except OSError as exc:
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete ya no está.") from exc
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (p.dev, p.ino, p.tamano, p.mtime_ns):
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete cambió mientras se preparaba.")


def _extraer_en_proceso(paquete: PaquetePendiente, temp: Path, fd: int,
                        modo: str, temp_fd: int, progreso=None,
                        total: int = 0) -> list[dict]:
    """Extrae ZIP en proceso hijo con timeout y kill de grupo; no bloquea el bucle."""
    datos = {"nombre": paquete.nombre, "tamano": paquete.tamano,
             "mtime_ns": paquete.mtime_ns, "firma": paquete.firma,
             "dev": paquete.dev, "ino": paquete.ino,
             "max_entrada": MAX_BYTES_ENTRADA, "max_total": MAX_BYTES_TOTAL,
             "max_ratio": MAX_RATIO_LEIDA}
    entorno = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
               "PYTHONPATH": str(Path(__file__).resolve().parents[2]),
               "LANG": "C.UTF-8"}
    os.set_inheritable(fd, True)
    os.set_inheritable(temp_fd, True)
    salida_fichero = tempfile.TemporaryFile(dir=temp)  # noqa: SIM115
    error_fichero = tempfile.TemporaryFile(dir=temp)  # noqa: SIM115
    limite_stdout, limite_stderr = 1024 * 1024, 64 * 1024
    parar = threading.Event()

    def _vigilar_salida() -> None:
        while not parar.wait(0.1):
            try:
                if (os.fstat(salida_fichero.fileno()).st_size > limite_stdout
                        or os.fstat(error_fichero.fileno()).st_size > limite_stderr):
                    with __import__("contextlib").suppress(OSError):
                        os.killpg(proc.pid, signal.SIGKILL)
                    return
            except OSError:
                return

    proc = subprocess.Popen(  # noqa: S603 — lista, sin shell, ruta absoluta
        [sys.executable, "-m", "zascarr.services.paquetes_worker", json.dumps(datos),
         modo, str(fd), str(temp), str(temp_fd)],
        stdin=subprocess.DEVNULL, stdout=salida_fichero, stderr=error_fichero,
        env=entorno, close_fds=True, pass_fds=(fd, temp_fd), start_new_session=True)
    vigilante = threading.Thread(target=_vigilar_salida, daemon=True)
    vigilante.start()
    parar_progreso = threading.Event()

    def _vigilar_progreso() -> None:
        ruta = temp / ".progreso"
        vistos = -1
        while not parar_progreso.wait(0.2):
            try:
                valor = int(ruta.read_text(encoding="ascii").strip() or "0")
            except (OSError, ValueError):
                continue
            if valor != vistos and progreso is not None:
                vistos = valor
                with __import__("contextlib").suppress(Exception):
                    progreso(valor, total)

    hilo_progreso = threading.Thread(target=_vigilar_progreso, daemon=True)
    hilo_progreso.start()
    try:
        try:
            proc.communicate(timeout=_ZIP_TIMEOUT)
        except subprocess.TimeoutExpired:
            with __import__("contextlib").suppress(OSError):
                os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            raise PaqueteExtraccionError("tiempo", "La extracción tardó demasiado.") from None
        error_fichero.seek(0)
        error = error_fichero.read(64 * 1024 + 1)
        if len(error) > 64 * 1024:
            raise PaqueteExtraccionError("salida", "La extracción escribió demasiados errores.")
        if proc.returncode != 0:
            raise PaqueteExtraccionError("extraccion", "La extracción falló.")
        salida_fichero.seek(0)
        salida = salida_fichero.read(1024 * 1024 + 1)
        if len(salida) > 1024 * 1024:
            raise PaqueteExtraccionError("extraccion", "La extracción devolvió demasiados datos.")
    finally:
        parar.set()
        parar_progreso.set()
        hilo_progreso.join(timeout=0.5)
        vigilante.join(timeout=1)
        salida_fichero.close()
        error_fichero.close()
    try:
        return list(json.loads(salida))
    except (ValueError, TypeError) as exc:
        raise PaqueteExtraccionError(
            "extraccion", "La extracción ZIP no devolvió resultado.") from exc


def _escribir_zip(paquete: PaquetePendiente, listado: ListadoPaquete, temp: Path,
                  fd: int, temp_fd: int, progreso=None) -> list[dict]:
    items: list[dict] = []
    try:
        z = zipfile.ZipFile(os.fdopen(os.dup(fd), "rb"))
    except (zipfile.BadZipFile, OSError) as exc:
        raise PaqueteExtraccionError("ilegible", "El paquete está dañado.") from exc
    with z:
        por_nombre = {e.nombre: e for e in listado.entradas if e.se_importa}
        vistos: set[str] = set()
        for info in z.infolist():
            if info.filename not in por_nombre or info.filename in vistos:
                continue
            vistos.add(info.filename)
            if info.flag_bits & 0x1:
                raise PaqueteExtraccionError("cifrado", "El paquete tiene contraseña.")
            nombre = _nombre_generado(len(items), Path(info.filename).suffix.lstrip(".") or "cbz")
            digest = hashlib.sha256()
            total = 0
            total_operacion = sum(int(i.get("bytes", 0)) for i in items)
            try:
                salida_fd = os.open(nombre, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                    | os.O_NOFOLLOW, 0o600, dir_fd=temp_fd)
                with z.open(info) as entrada, os.fdopen(salida_fd, "wb") as salida:
                    while bloque := entrada.read(_BLOQUE):
                        total += len(bloque)
                        if total > MAX_BYTES_ENTRADA:
                            raise PaqueteExtraccionError(
                                "demasiado_grande", "Un fichero de dentro es demasiado grande.")
                        ratio = total / max(info.compress_size, 1)
                        if info.compress_size and ratio > MAX_RATIO_LEIDA:
                            raise PaqueteExtraccionError(
                                "ratio", "El paquete está demasiado comprimido.")
                        if total_operacion + total > MAX_BYTES_TOTAL:
                            raise PaqueteExtraccionError(
                                "tamano_total", "El paquete extraído es demasiado grande.")
                        digest.update(bloque)
                        salida.write(bloque)
                    salida.flush()
                    os.fsync(salida.fileno())
            except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
                raise PaqueteExtraccionError(
                    "ilegible", "Un fichero de dentro no se pudo leer."
                ) from exc
            if total != info.file_size:
                raise PaqueteExtraccionError("tamano", "El tamaño extraído no coincide.")
            items.append(
                {
                    "nombre": nombre,
                    "origen": info.filename,
                    "bytes": total,
                    "sha256": digest.hexdigest(),
                    "estado": "verificado",
                }
            )
            if progreso is not None:
                progreso(len(items))
    return items


def _escribir_rar(paquete: PaquetePendiente, listado: ListadoPaquete, temp: Path,
                  fd: int, temp_fd: int, progreso=None) -> list[dict]:
    if not lector_rar.disponible():
        raise PaqueteExtraccionError("herramienta_ausente", "Falta la herramienta para leer RAR.")
    if len(listado.entradas) > lector_rar.RAR_MAX_ENTRADAS:
        raise PaqueteExtraccionError("demasiadas_entradas", "El paquete tiene demasiados archivos.")
    items: list[dict] = []
    with lector_rar.carpeta_temporal(temp) as casa:
        for entrada in listado.entradas:
            if not entrada.se_importa:
                continue
            if entrada.tamano > 2 * 1024**3:
                raise PaqueteExtraccionError("demasiado_grande", "Un fichero es demasiado grande.")
            nombre = _nombre_generado(len(items), entrada.nombre.rsplit(".", 1)[-1] or "cbz")
            destino = temp / nombre
            try:
                total = lector_rar.extraer_entrada_a(
                    Path(f"/proc/self/fd/{fd}"), entrada, destino, entrada.tamano,
                    temporal=casa, pass_fds=(fd,), destino_dir_fd=temp_fd)
            except lector_rar.ErrorRar as exc:
                raise PaqueteExtraccionError(
                    "ilegible", "El paquete está dañado o cifrado.") from exc
            h = hashlib.sha256()
            fd_out = os.open(nombre, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=temp_fd)
            try:
                while bloque := os.read(fd_out, _BLOQUE):
                    h.update(bloque)
            finally:
                os.close(fd_out)
            items.append({"nombre": nombre, "origen": entrada.nombre, "bytes": total,
                          "sha256": h.hexdigest(), "estado": "verificado"})
            if progreso is not None:
                progreso(len(items))
    return items


def _decodificar_imagen(datos: bytes) -> None:
    import io

    from PIL import Image

    try:
        with Image.open(io.BytesIO(datos)) as img:
            ancho, alto = img.size
            if ancho * alto > MAX_PIXELES_PORTADA:
                raise PaqueteExtraccionError(
                    "pixeles", "La primera página tiene demasiados píxeles.")
            img.load()
    except PaqueteExtraccionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise PaqueteExtraccionError(
            "imagen", "La primera imagen no se puede decodificar.") from exc


def _verificar_contenido(items: list[dict], temp: Path, temp_fd: int | None = None) -> None:
    """Firma/cabecera y primera imagen de cada tebeo extraído; falla cerrado."""


    propio = temp_fd is None
    if propio:
        temp_fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        _verificar_contenido_fd(items, temp, temp_fd)
    finally:
        if propio:
            os.close(temp_fd)


def _verificar_contenido_fd(items: list[dict], temp: Path, temp_fd: int) -> None:
    esperados = {i["nombre"] for i in items}
    reales = set(os.listdir(temp_fd))
    if reales != esperados:
        raise PaqueteExtraccionError("verificacion", "El temporal tiene ficheros inesperados.")
    for item in items:

        ext = Path(item["nombre"]).suffix.lower()
        fd_item = os.open(item["nombre"], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=temp_fd)
        try:
            with os.fdopen(os.dup(fd_item), "rb") as fh:
                firma = firma_de_bytes(fh.read(512))
            if ext == ".cbz" and firma is not Firma.ZIP:
                raise PaqueteExtraccionError("firma", "Un tebeo dice ZIP pero no lo es.")
            if ext == ".cbr" and firma is not Firma.RAR:
                raise PaqueteExtraccionError("firma", "Un tebeo dice RAR pero no lo es.")
            if firma is Firma.ZIP:
                try:
                    with _zip.ZipFile(os.fdopen(os.dup(fd_item), "rb")) as z:
                        imagen = next((n for n in z.namelist()
                                       if Path(n).suffix.lower() in _EXTS_IMAGEN), None)
                        if imagen is None:
                            raise PaqueteExtraccionError("sin_imagen", "Un tebeo no tiene páginas.")
                        if z.getinfo(imagen).file_size > MAX_ENTRADA_LEIDA:
                            raise PaqueteExtraccionError(
                                "tamano", "La primera página es demasiado grande.")
                        datos = z.read(imagen)
                        _decodificar_imagen(datos)
                except PaqueteExtraccionError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    raise PaqueteExtraccionError(
                        "ilegible", "Un tebeo extraído no se puede abrir.") from exc
            elif firma is Firma.RAR:
                if not lector_rar.disponible():
                    raise PaqueteExtraccionError(
                        "herramienta_ausente", "Falta la herramienta para leer RAR.")
                with lector_rar.carpeta_temporal(temp) as casa:
                    fd_rar = os.open(item["nombre"], os.O_RDONLY | os.O_NOFOLLOW,
                                     dir_fd=temp_fd)
                    try:
                        try:
                            listado = lector_rar.listar(
                                Path(f"/proc/self/fd/{fd_rar}"), temporal=casa,
                                pass_fds=(fd_rar,))
                        except lector_rar.ErrorRar as exc:
                            raise PaqueteExtraccionError(
                                "ilegible", "Un tebeo RAR extraído no se puede listar.") from exc
                        entrada = next((e for e in listado.entradas
                                        if not e.es_directorio and not e.cifrada
                                        and Path(e.nombre).suffix.lower() in _EXTS_IMAGEN), None)
                        if entrada is None:
                            raise PaqueteExtraccionError(
                                "sin_imagen", "Un tebeo no tiene páginas.")
                        if entrada.tamano > MAX_ENTRADA_LEIDA:
                            raise PaqueteExtraccionError(
                                "tamano", "La primera página es demasiado grande.")
                        salida = temp / f"imagen-{fd_rar}"
                        try:
                            lector_rar.extraer_entrada_a(
                                Path(f"/proc/self/fd/{fd_rar}"), entrada, salida,
                                MAX_ENTRADA_LEIDA, temporal=casa,
                                pass_fds=(fd_rar,), destino_dir_fd=temp_fd)
                        except lector_rar.ErrorRar as exc:
                            raise PaqueteExtraccionError(
                                "ilegible", "La primera imagen RAR no se pudo extraer.") from exc
                        fd_img = os.open(salida.name, os.O_RDONLY | os.O_NOFOLLOW,
                                         dir_fd=temp_fd)
                        try:
                            datos = b""
                            while bloque := os.read(fd_img, 1024 * 1024):
                                datos += bloque
                                if len(datos) > MAX_ENTRADA_LEIDA:
                                    raise PaqueteExtraccionError(
                                        "tamano", "La primera página es demasiado grande.")
                            _decodificar_imagen(datos)
                        finally:
                            os.close(fd_img)
                            with __import__("contextlib").suppress(OSError):
                                os.unlink(salida.name, dir_fd=temp_fd)
                    finally:
                        os.close(fd_rar)
        finally:
            os.close(fd_item)


def _verificar_items(items: list[dict], temp: Path, temp_fd: int, total_listado: int) -> None:
    total = 0
    for item in items:
        try:
            st = os.stat(item["nombre"], dir_fd=temp_fd, follow_symlinks=False)
        except OSError as exc:
            raise PaqueteExtraccionError(
                "verificacion", "Un fichero extraído no es correcto.") from exc
        if not stat.S_ISREG(st.st_mode) or st.st_size != item["bytes"]:
            raise PaqueteExtraccionError("verificacion", "Un fichero extraído no es correcto.")
        if st.st_size > 2 * 1024**3:
            raise PaqueteExtraccionError("demasiado_grande", "Un fichero es demasiado grande.")
        total += st.st_size
    if total != total_listado:
        raise PaqueteExtraccionError("verificacion", "Lo extraído no coincide con el listado.")


async def crear_operacion(s: AsyncSession, paquete: PaquetePendiente) -> PaqueteOperacion:
    _comprobar_original(paquete)
    clave = clave_identidad(paquete)
    viva = (
        await s.execute(
            select(PaqueteOperacion).where(
                PaqueteOperacion.paquete_clave == clave,
                PaqueteOperacion.estado.in_(
                    [
                        PaqueteEstado.LISTANDO, PaqueteEstado.EXTRAYENDO,
                        PaqueteEstado.VERIFICANDO, PaqueteEstado.PUBLICANDO,
                        PaqueteEstado.IMPORTANDO, PaqueteEstado.IMPORTADO,
                    ]
                ),
            ).order_by(PaqueteOperacion.creada.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if viva is not None:
        return viva
    op = PaqueteOperacion(
        paquete_clave=clave,
        paquete_path=str(paquete.ruta),
        paquete_dev=paquete.dev,
        paquete_ino=paquete.ino,
        paquete_size=paquete.tamano,
        paquete_mtime_ns=paquete.mtime_ns,
        firma=paquete.firma,
        estado=PaqueteEstado.LISTANDO,
    )
    s.add(op)
    try:
        await s.commit()
    except IntegrityError:
        await s.rollback()
        viva = (await s.execute(select(PaqueteOperacion).where(
            PaqueteOperacion.paquete_clave == clave,
            PaqueteOperacion.estado.in_([PaqueteEstado.LISTANDO, PaqueteEstado.EXTRAYENDO,
                                         PaqueteEstado.VERIFICANDO, PaqueteEstado.PUBLICANDO,
                                         PaqueteEstado.IMPORTANDO])))).scalar_one()
        return viva
    await s.refresh(op)
    return op


async def extraer_y_verificar(s: AsyncSession, operacion_id: UUID, *,
                             conservar_temporal: bool = False,
                             progreso=None) -> ResultadoExtraccion:
    op = await s.get(PaqueteOperacion, operacion_id, with_for_update=True)
    if op is None:
        raise PaqueteExtraccionError("no_existe", "La operación no existe.")
    if op.estado is PaqueteEstado.VERIFICADO and op.temp_dir:
        # Un segundo POST reutiliza la extracción ya verificada; no reextrae.
        return ResultadoExtraccion(
            operacion_id=op.id, items=tuple(op.items or ()), total_bytes=op.total_bytes or 0)
    if op.estado not in (PaqueteEstado.LISTANDO, PaqueteEstado.EXTRAYENDO,
                         PaqueteEstado.VERIFICANDO):
        raise PaqueteExtraccionError("estado", "La operación no es reanudable.")
    paquete = PaquetePendiente(
        ruta=Path(op.paquete_path),
        raiz=Path(op.paquete_path).parent,
        relativa=Path(op.paquete_path).name,
        nombre=Path(op.paquete_path).name,
        tamano=op.paquete_size,
        mtime_ns=op.paquete_mtime_ns,
        firma=op.firma,
        estado="listo",
        causa="",
        dev=op.paquete_dev,
        ino=op.paquete_ino,
    )
    base = _base_temporal()
    try:
        fd = os.open(op.paquete_path, os.O_RDONLY | os.O_NOFOLLOW)
        st = os.fstat(fd)
        if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (
                op.paquete_dev, op.paquete_ino, op.paquete_size, op.paquete_mtime_ns):
            os.close(fd)
            raise PaqueteExtraccionError("paquete_cambiado", "El paquete cambió antes de extraer.")
        paquete = PaquetePendiente(**{**paquete.__dict__, "fd": fd})
    except OSError as exc:
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete ya no está.") from exc
    try:
        temp, temp_fd = _crear_temp(base, str(op.id))
    except BaseException:
        with __import__("contextlib").suppress(OSError):
            os.close(paquete.fd)
        raise
    try:
        os.chmod(temp, 0o700)
        op.temp_dir = str(temp)
        op.estado = PaqueteEstado.EXTRAYENDO
        s.add(op)
        await s.commit()
        try:
            listado = listar_paquete(paquete)
        except PaqueteError as exc:
            raise PaqueteExtraccionError("listado", exc.causa) from exc
        comprobar_espacio(base, listado.bytes_estimados or 1,
                          "extraer el paquete")
        total_items = sum(1 for e in listado.entradas if e.se_importa)

        def _progreso(hechos: int, total: int) -> None:
            if progreso is not None:
                progreso(hechos, total or total_items)

        items = await asyncio.to_thread(
            _extraer_en_proceso, paquete, temp, paquete.fd,
            "zip" if paquete.firma == "ZIP" else "rar", temp_fd,
            _progreso, total_items)
        _progreso(len(items), total_items)
        _verificar_contenido(items, temp, temp_fd)
        op.estado = PaqueteEstado.VERIFICANDO
        op.items = list(items)
        s.add(op)
        await s.commit()
        _verificar_items(items, temp, temp_fd, listado.bytes_estimados)
        op.estado = PaqueteEstado.VERIFICADO
        op.total_entradas = len(items)
        op.total_bytes = sum(int(i["bytes"]) for i in items)
        op.finalizada = __import__("datetime").datetime.now(__import__("datetime").UTC)
        op.temp_dir = str(temp) if conservar_temporal else None
        s.add(op)
        await s.commit()
        with __import__("contextlib").suppress(OSError):
            os.close(paquete.fd)
        with __import__("contextlib").suppress(OSError):
            os.close(temp_fd)
        if conservar_temporal:
            return ResultadoExtraccion(
                operacion_id=op.id, items=tuple(items), total_bytes=op.total_bytes)
        if not _borrar_temp(temp):
            op = await s.get(PaqueteOperacion, operacion_id)
            if op is not None:
                op.temp_dir = str(temp)
                s.add(op)
                await s.commit()
            raise PaqueteExtraccionError("limpieza", "El temporal no se pudo borrar.")
        return ResultadoExtraccion(
            operacion_id=op.id, items=tuple(items), total_bytes=op.total_bytes
        )
    except BaseException:
        await s.rollback()
        with __import__("contextlib").suppress(OSError):
            os.close(paquete.fd)
        with __import__("contextlib").suppress(OSError):
            os.close(temp_fd)
        borrado = _borrar_temp(temp)
        op = await s.get(PaqueteOperacion, operacion_id)
        if op is not None:
            op.estado = PaqueteEstado.ERROR
            op.error_codigo = getattr(__import__("sys").exc_info()[1], "codigo", "error")
            op.error_mensaje = getattr(
                __import__("sys").exc_info()[1], "mensaje", "No se pudo extraer."
            )
            op.temp_dir = None if borrado else str(temp)
            s.add(op)
            await s.commit()
        raise


async def limpiar_huerfanos(s: AsyncSession) -> int:
    """Marca error las operaciones vivas de un arranque anterior y borra sus temporales."""
    # Primero staging de publicaciones interrumpidas: el primer barrido las
    # convierte a ERROR y, si se hiciera después, ya no se encontrarían.
    atascadas = (await s.execute(select(PaqueteOperacion).where(
        PaqueteOperacion.estado.in_(
            [PaqueteEstado.PUBLICANDO, PaqueteEstado.IMPORTANDO])))).scalars().all()
    for op in atascadas:
        if op.staging_dir:
            _borrar_temp(Path(op.staging_dir))
        op.estado = PaqueteEstado.ERROR
        op.error_codigo = "interrumpida"
        op.error_mensaje = "La publicación se interrumpió; se puede reintentar."
        op.staging_dir = None
        s.add(op)
    if atascadas:
        await s.commit()
    vivas = (
        (
            await s.execute(
                select(PaqueteOperacion).where(
                    PaqueteOperacion.temp_dir.is_not(None),
                    PaqueteOperacion.estado.in_(
                        [PaqueteEstado.LISTANDO, PaqueteEstado.EXTRAYENDO,
                         PaqueteEstado.VERIFICANDO, PaqueteEstado.ERROR]))
            )
        )
        .scalars()
        .all()
    )
    for op in vivas:
        borrado = True
        if op.temp_dir:
            borrado = _borrar_temp(Path(op.temp_dir))
        op.estado = PaqueteEstado.ERROR
        op.error_codigo = "interrumpida"
        op.error_mensaje = "La extracción se interrumpió; se puede reintentar."
        op.temp_dir = None if borrado else op.temp_dir
        s.add(op)
    if vivas:
        await s.commit()
    # El recuento devuelto incluye ambas familias; se devuelve al final.
    total_huerfanos = len(vivas) + len(atascadas)
    try:
        base = _base_temporal()
        referenciados = {Path(x) for x in (await s.execute(
            select(PaqueteOperacion.temp_dir).where(
                PaqueteOperacion.temp_dir.is_not(None)))).scalars()}
        for hijo in base.iterdir():
            if hijo not in referenciados and hijo.is_dir():
                _borrar_temp(hijo)
    except OSError:
        logger.warning("paquetes.barrido_temporales_fallido")
    return total_huerfanos
