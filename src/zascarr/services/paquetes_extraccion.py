"""#344 BL-PACK1 corte 3: extracción y verificación durable de paquetes.

Solo escribe en un temporal propio bajo `covers_cache_path/.paquetes`; nunca publica,
importa ni toca la biblioteca/Descargas. El original permanece intacto.
Termina en `verificado` (corte 4 publica).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import stat
import tempfile
import zipfile
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
    firma_de,
)
from zascarr.models import PaqueteEstado, PaqueteOperacion
from zascarr.services.paquetes import (
    ListadoPaquete,
    PaqueteError,
    PaquetePendiente,
    listar_paquete,
)
from zascarr.utils import lector_rar
from zascarr.utils.espacio import comprobar_espacio

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
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(base, 0o700)
    fd = os.open(base, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        real = Path(os.path.realpath(f"/proc/self/fd/{fd}"))
    finally:
        os.close(fd)
    prohibidas: list[Path] = []
    for valor in (getattr(ajustes, "library_path", None),
                  getattr(ajustes, "transmission_download_dir", None),
                  getattr(ajustes, "amule_incoming_dir", None),
                  getattr(ajustes, "downloads_path", None)):
        if valor:
            prohibidas.append(Path(valor))
    for prohibida in prohibidas:
        try:
            if real == prohibida or prohibida in real.parents:
                raise PaqueteExtraccionError(
                    "temporal_inseguro", "El temporal está dentro de una carpeta vigilada.")
        except OSError:
            continue
    return real


def _nombre_generado(indice: int, tipo: str) -> str:
    return f"{indice + 1:04d}.{tipo.lower()}"


def _comprobar_original(p: PaquetePendiente) -> None:
    try:
        st = p.ruta.stat(follow_symlinks=False)
    except OSError as exc:
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete ya no está.") from exc
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (p.dev, p.ino, p.tamano, p.mtime_ns):
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete cambió mientras se preparaba.")


def _escribir_zip(paquete: PaquetePendiente, listado: ListadoPaquete, temp: Path,
                  fd: int) -> list[dict]:
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
            destino = temp / nombre
            digest = hashlib.sha256()
            total = 0
            try:
                with z.open(info) as entrada, open(destino, "xb") as salida:
                    while bloque := entrada.read(_BLOQUE):
                        total += len(bloque)
                        if total > 2 * 1024 ** 3:
                            raise PaqueteExtraccionError(
                                "demasiado_grande", "Un fichero de dentro es demasiado grande.")
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
    return items


def _escribir_rar(paquete: PaquetePendiente, listado: ListadoPaquete, temp: Path,
                  fd: int) -> list[dict]:
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
                    temporal=casa, pass_fds=(fd,))
            except lector_rar.ErrorRar as exc:
                raise PaqueteExtraccionError(
                    "ilegible", "El paquete está dañado o cifrado.") from exc
            h = hashlib.sha256()
            with open(destino, "rb") as f:
                while bloque := f.read(_BLOQUE):
                    h.update(bloque)
            items.append({"nombre": nombre, "origen": entrada.nombre, "bytes": total,
                          "sha256": h.hexdigest(), "estado": "verificado"})
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


def _verificar_contenido(items: list[dict], temp: Path) -> None:
    """Firma/cabecera y primera imagen de cada tebeo extraído; falla cerrado."""
    import zipfile as _zip


    esperados = {i["nombre"] for i in items}
    reales = {p.name for p in temp.iterdir() if p.is_file()}
    if reales != esperados:
        raise PaqueteExtraccionError("verificacion", "El temporal tiene ficheros inesperados.")
    for item in items:
        ruta = temp / item["nombre"]
        ext = ruta.suffix.lower()
        firma = firma_de(ruta)
        if ext == ".cbz" and firma is not Firma.ZIP:
            raise PaqueteExtraccionError("firma", "Un tebeo dice ZIP pero no lo es.")
        if ext == ".cbr" and firma is not Firma.RAR:
            raise PaqueteExtraccionError("firma", "Un tebeo dice RAR pero no lo es.")
        if firma is Firma.ZIP:
            try:
                with _zip.ZipFile(ruta) as z:
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
                try:
                    listado = lector_rar.listar(ruta, temporal=casa)
                except lector_rar.ErrorRar as exc:
                    raise PaqueteExtraccionError(
                        "ilegible", "Un tebeo RAR extraído no se puede listar.") from exc
                entrada = next((e for e in listado.entradas
                                if not e.es_directorio and not e.cifrada
                                and Path(e.nombre).suffix.lower() in _EXTS_IMAGEN), None)
                if entrada is None:
                    raise PaqueteExtraccionError("sin_imagen", "Un tebeo no tiene páginas.")
                if entrada.tamano > MAX_ENTRADA_LEIDA:
                    raise PaqueteExtraccionError(
                            "tamano", "La primera página es demasiado grande.")
                salida = casa / "imagen"
                try:
                    lector_rar.extraer_entrada_a(ruta, entrada, salida, MAX_ENTRADA_LEIDA,
                                                temporal=casa)
                except lector_rar.ErrorRar as exc:
                    raise PaqueteExtraccionError(
                        "ilegible", "La primera imagen RAR no se pudo extraer.") from exc
                _decodificar_imagen(salida.read_bytes())
                salida.unlink(missing_ok=True)

def _verificar_items(items: list[dict], temp: Path, total_listado: int) -> None:
    total = 0
    for item in items:
        ruta = temp / item["nombre"]
        st = ruta.lstat()
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
                        PaqueteEstado.LISTANDO,
                        PaqueteEstado.EXTRAYENDO,
                        PaqueteEstado.VERIFICANDO,
                        PaqueteEstado.PUBLICANDO,
                        PaqueteEstado.IMPORTANDO,
                    ]
                ),
            )
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


async def extraer_y_verificar(s: AsyncSession, operacion_id: UUID) -> ResultadoExtraccion:
    op = await s.get(PaqueteOperacion, operacion_id, with_for_update=True)
    if op is None:
        raise PaqueteExtraccionError("no_existe", "La operación no existe.")
    if op.estado in (PaqueteEstado.VERIFICADO, PaqueteEstado.ERROR):
        raise PaqueteExtraccionError("estado", "La operación ya terminó.")
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
    temp = Path(tempfile.mkdtemp(prefix=f"{op.id}-", dir=base))
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
        if paquete.firma == "ZIP":
            items = await asyncio.wait_for(asyncio.to_thread(
                _escribir_zip, paquete, listado, temp, paquete.fd), timeout=900)
        elif paquete.firma == "RAR":
            items = await asyncio.wait_for(asyncio.to_thread(
                _escribir_rar, paquete, listado, temp, paquete.fd), timeout=900)
        else:
            raise PaqueteExtraccionError("formato", "El paquete no es RAR ni ZIP.")
        _verificar_contenido(items, temp)
        op.estado = PaqueteEstado.VERIFICANDO
        op.items = list(items)
        s.add(op)
        await s.commit()
        _verificar_items(items, temp, listado.bytes_estimados)
        op.estado = PaqueteEstado.VERIFICADO
        op.total_entradas = len(items)
        op.total_bytes = sum(int(i["bytes"]) for i in items)
        op.finalizada = __import__("datetime").datetime.now(__import__("datetime").UTC)
        op.temp_dir = None
        s.add(op)
        await s.commit()
        with __import__("contextlib").suppress(OSError):
            os.close(paquete.fd)
        shutil.rmtree(temp, ignore_errors=True)
        return ResultadoExtraccion(
            operacion_id=op.id, items=tuple(items), total_bytes=op.total_bytes
        )
    except BaseException:
        await s.rollback()
        with __import__("contextlib").suppress(OSError):
            os.close(paquete.fd)
        shutil.rmtree(temp, ignore_errors=True)
        op = await s.get(PaqueteOperacion, operacion_id)
        if op is not None:
            op.estado = PaqueteEstado.ERROR
            op.error_codigo = getattr(__import__("sys").exc_info()[1], "codigo", "error")
            op.error_mensaje = getattr(
                __import__("sys").exc_info()[1], "mensaje", "No se pudo extraer."
            )
            op.temp_dir = None
            s.add(op)
            await s.commit()
        raise


async def limpiar_huerfanos(s: AsyncSession) -> int:
    """Marca error las operaciones vivas de un arranque anterior y borra sus temporales."""
    vivas = (
        (
            await s.execute(
                select(PaqueteOperacion).where(
                    PaqueteOperacion.estado.in_(
                        [
                            PaqueteEstado.LISTANDO,
                            PaqueteEstado.EXTRAYENDO,
                            PaqueteEstado.VERIFICANDO,
                        ]
                    )
                )
            )
        )
        .scalars()
        .all()
    )
    for op in vivas:
        if op.temp_dir:
            shutil.rmtree(op.temp_dir, ignore_errors=True)
        op.estado = PaqueteEstado.ERROR
        op.error_codigo = "interrumpida"
        op.error_mensaje = "La extracción se interrumpió; se puede reintentar."
        op.temp_dir = None
        s.add(op)
    if vivas:
        await s.commit()
    return len(vivas)
