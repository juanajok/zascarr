"""#344 BL-PACK1 corte 3: extracción y verificación durable de paquetes.

Solo escribe en un temporal propio bajo `covers_cache_path/.paquetes`; nunca publica,
importa ni toca la biblioteca/Descargas. El original permanece intacto.
Termina en `verificado` (corte 4 publica).
"""

from __future__ import annotations

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
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.formato_contenedor import Firma, firma_de
from zascarr.models import PaqueteEstado, PaqueteOperacion
from zascarr.services.paquetes import (
    ListadoPaquete,
    PaqueteError,
    PaquetePendiente,
    listar_paquete,
)
from zascarr.utils import lector_rar

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
    base = Path(get_settings().covers_cache_path) / ".paquetes"
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(base, 0o700)
    return base


def _nombre_generado(indice: int, tipo: str) -> str:
    return f"{indice + 1:04d}.{tipo.lower()}"


def _comprobar_original(p: PaquetePendiente) -> None:
    try:
        st = p.ruta.stat(follow_symlinks=False)
    except OSError as exc:
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete ya no está.") from exc
    if (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns) != (p.dev, p.ino, p.tamano, p.mtime_ns):
        raise PaqueteExtraccionError("paquete_cambiado", "El paquete cambió mientras se preparaba.")


def _escribir_zip(paquete: PaquetePendiente, listado: ListadoPaquete, temp: Path) -> list[dict]:
    items: list[dict] = []
    try:
        z = zipfile.ZipFile(paquete.ruta)
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


def _escribir_rar(paquete: PaquetePendiente, listado: ListadoPaquete, temp: Path) -> list[dict]:
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
            try:
                datos = lector_rar.leer_entrada(
                    paquete.ruta, entrada, entrada.tamano + 1, temporal=casa
                )
            except lector_rar.ErrorRar as exc:
                raise PaqueteExtraccionError(
                    "ilegible", "El paquete está dañado o cifrado."
                ) from exc
            nombre = _nombre_generado(len(items), entrada.nombre.rsplit(".", 1)[-1] or "cbz")
            destino = temp / nombre
            with open(destino, "xb") as f:
                f.write(datos)
                f.flush()
                os.fsync(f.fileno())
            items.append(
                {
                    "nombre": nombre,
                    "origen": entrada.nombre,
                    "bytes": len(datos),
                    "sha256": hashlib.sha256(datos).hexdigest(),
                    "estado": "verificado",
                }
            )
    return items


def _verificar_contenido(items: list[dict], temp: Path) -> None:
    """Firma/cabecera y primera imagen de cada tebeo extraído; falla cerrado."""
    import io
    import zipfile as _zip

    from PIL import Image

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
                                   if Path(n).suffix.lower() in
                                   {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}), None)
                    if imagen is None:
                        raise PaqueteExtraccionError("sin_imagen", "Un tebeo no tiene páginas.")
                    datos = z.read(imagen)
                    with Image.open(io.BytesIO(datos)) as img:
                        img.verify()
            except PaqueteExtraccionError:
                raise
            except Exception as exc:  # noqa: BLE001 — cualquier cabecera/imagen rota
                raise PaqueteExtraccionError(
                    "ilegible", "Un tebeo extraído no se puede abrir.") from exc


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
    await s.commit()
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
        if paquete.firma == "ZIP":
            items = _escribir_zip(paquete, listado, temp)
        elif paquete.firma == "RAR":
            items = _escribir_rar(paquete, listado, temp)
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
        shutil.rmtree(temp, ignore_errors=True)
        return ResultadoExtraccion(
            operacion_id=op.id, items=tuple(items), total_bytes=op.total_bytes
        )
    except BaseException:
        await s.rollback()
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
