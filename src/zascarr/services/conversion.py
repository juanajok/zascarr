# ruff: noqa: E501
"""#478 / BL-CNV1: convertir un CBR en CBZ desde la ficha, reversible y verificado.

Un solo trabajo a la vez, locks por `File.id` y cerrojo de ciclo; límite duro de 150 MiB; el
original se aparta en la cuarentena de la biblioteca y la MISMA fila `File` pasa a describir el CBZ.
No toca la relación editorial, `metadata_source` ni `locked_fields`. Sin migración: el diario y el
estado viven en `File.metadata_` y en `.zascarr/`.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, FileFormat, Issue
from zascarr.services.compartidos import EstadoComparticion, estado_de_comparticion
from zascarr.services.comprobacion_disco import CLAVE_CERROJO_CICLO
from zascarr.services.conversion_cbr import (
    ConversionBloqueadaError,
    MotivoConversion,
    analizar,
    construir_cbz,
)
from zascarr.services.tagger import bloqueo_de_fichero, motor_de
from zascarr.services.tokens_revision import (
    ConversionFirmada,
    crear_token_conversion,
    verificar_token_conversion,
)
from zascarr.services.vinculacion import (
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
)
from zascarr.utils import lector_rar
from zascarr.utils.bloqueo_archivo import bloquear_archivo
from zascarr.utils.espacio import EspacioInsuficienteError, comprobar_espacio

logger = structlog.get_logger()

MAX_CONVERSION = 150 * 1024 * 1024
MARCADOR_DIARIO = "conversion_diario"
_VERSION = 1

MENSAJES = {
    MotivoConversion.ARCHIVO_AUSENTE: "El archivo ya no está en el disco; no se toca.",
    MotivoConversion.NO_ES_CBR: "Ese archivo no es un CBR; no se puede convertir.",
    MotivoConversion.YA_EXISTE_CBZ: "Ya existe un CBZ con ese nombre; no se sobrescribe.",
    MotivoConversion.DEMASIADO_GRANDE: "El CBR supera el máximo de 150 MB; no se convierte.",
    MotivoConversion.SIN_ESPACIO: "No hay espacio suficiente para el CBZ; no se convierte.",
    MotivoConversion.OTRO_DISCO: "El CBZ y el original estarían en discos distintos; no se convierte.",
    MotivoConversion.CIFRADO: "El CBR está cifrado; no se puede convertir.",
    MotivoConversion.MULTIVOLUMEN: "El CBR es multivolumen; no se puede convertir.",
    MotivoConversion.PAQUETE: "El CBR contiene otro archivo de tebeo; no se convierte.",
    MotivoConversion.ILEGIBLE: "El CBR está dañado o no se puede leer; no se convierte.",
    MotivoConversion.HERRAMIENTA_AUSENTE: "Falta la herramienta de RAR; no se convierte.",
    MotivoConversion.LECTOR_DESACTIVADO: "El lector de RAR está apagado; no se convierte.",
    MotivoConversion.NOMBRE_NO_SEGURO: "El CBR trae un nombre no seguro; no se convierte.",
    MotivoConversion.COMICINFO_DUPLICADO: "El CBR trae más de un ComicInfo.xml; no se convierte.",
    MotivoConversion.PROPUESTA_DESACTUALIZADA: "El archivo cambió desde la vista previa; no se ha tocado nada.",
    MotivoConversion.COMPARTIDO: "Parece compartido por un programa de descargas.",
    MotivoConversion.NO_SE_SABE: "No se puede saber si está compartido.",
    MotivoConversion.CONFLICTO_DE_BLOQUEO: "Otra operación coincidió; no se ha convertido.",
    MotivoConversion.RESULTADO_INCIERTO: "No se sabe si la conversión llegó a publicarse.",
}


@dataclass(frozen=True)
class VistaConversion:
    file_id: str
    serie_id: str | None
    nombre_original: str
    nombre_nuevo: str
    metodo: str
    tamano_entrada: int
    estimado_salida: int
    espacio_libre: int | None
    necesario: int
    puede_convertir: bool
    motivo: str | None
    mensaje: str
    advertencia: str | None = None
    forzable: bool = False
    token: str | None = None


@dataclass
class ResultadoConversion:
    version: int
    tipo: str
    operacion_id: str
    file_id: str
    resultado: Literal["convertida", "ya_convertida", "revertida", "ya_revertida", "omitida"]
    motivo: str | None
    mensaje: str
    repetida: bool = False
    advertencia: str | None = None
    forzado_compartido: bool = False
    metodo: str | None = None
    antes: dict = field(default_factory=dict)
    despues: dict = field(default_factory=dict)
    fecha: str | None = None


def _ahora_iso() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _fecha() -> str:
    return datetime.now(UTC).isoformat()


def _fsync_dir(ruta: Path) -> None:
    try:
        fd = os.open(str(ruta), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _cuarentena(settings) -> Path:
    return Path(settings.library_path) / ".zascarr" / "originales"


def _diario(settings) -> Path:
    return Path(settings.library_path) / ".zascarr" / "diario"


def _conflicto(motivo: MotivoConversion, mensaje: str | None = None) -> ResultadoConversion:
    return ResultadoConversion(
        _VERSION, "conversion", "", "", "omitida", motivo.value,
        mensaje or MENSAJES.get(motivo, "No se ha convertido nada."))


def _vista_bloqueada(file: File, motivo: MotivoConversion, mensaje: str | None = None) -> VistaConversion:
    return VistaConversion(
        str(file.id), None, file.file_name, file.file_name, "", file.file_size_bytes or 0, 0,
        None, 0, False, motivo.value, mensaje or MENSAJES.get(motivo, "No se puede convertir."))


class ConversionDeArchivo:
    def __init__(self, db: AsyncSession, *, secret: str, ahora: float | None = None,
                 lector=lector_rar, settings=None):
        self._db = db
        self._secret = secret
        self._ahora = ahora
        self._lector = lector
        self._settings = settings or get_settings()

    # ── tokens/estado ───────────────────────────────────────────────────────
    def _token(self, f: File, *, operacion: str, metodo: str, accion: str) -> str:
        sha = f.sha256_hash or _sha256(Path(f.file_path))
        st = Path(f.file_path).stat()
        return crear_token_conversion(ConversionFirmada(
            file_id=str(f.id), operacion=operacion, ruta=f.file_path, tamano=st.st_size,
            mtime_ns=st.st_mtime_ns, sha256=sha, metodo=metodo, accion=accion),
            self._secret, ahora=self._ahora)

    def _estado_meta(self, f: File) -> dict | None:
        meta = f.metadata_ if isinstance(f.metadata_, dict) else {}
        conv = meta.get("conversion")
        return conv if isinstance(conv, dict) else None

    def _compartida(self, path: Path):
        return estado_de_comparticion(path, settings=self._settings)

    def _aviso(self, decision) -> str | None:
        if decision.estado is EstadoComparticion.NO_COMPARTIDO:
            return None
        return (f"Cuidado: este archivo parece compartido ({decision.causa}). "
                "Si conviertes, la siembra puede romperse.")

    # ── vista previa ────────────────────────────────────────────────────────
    async def previsualizar(self, serie_id: UUID, file_id: UUID) -> VistaConversion:
        f = await self._leer(serie_id, file_id)
        if f is None:
            raise TokenInvalidoError("Ese archivo no existe o no pertenece a esta serie.")
        ruta = Path(f.file_path)
        nombre_nuevo = ruta.with_suffix(".cbz").name
        if f.file_format is not FileFormat.CBR:
            return _vista_bloqueada(f, MotivoConversion.NO_ES_CBR)
        try:
            analisis = await asyncio.to_thread(analizar, ruta, lector=self._lector)
        except ConversionBloqueadaError as exc:
            return _vista_bloqueada(f, exc.motivo, exc.mensaje)
        destino = ruta.with_suffix(".cbz")
        if destino.exists() and destino != ruta:
            return _vista_bloqueada(f, MotivoConversion.YA_EXISTE_CBZ)
        try:
            comprobar_espacio(destino.parent, max(analisis.estimado_salida, 1), "conversión")
        except EspacioInsuficienteError as exc:
            v = _vista_bloqueada(f, MotivoConversion.SIN_ESPACIO, str(exc))
            return VistaConversion(**{**v.__dict__, "espacio_libre": exc.bytes_libres})
        decision = await self._compartida(ruta)
        aviso = self._aviso(decision)
        token = self._token(f, operacion=str(uuid.uuid4()), metodo=analisis.metodo, accion="convertir")
        return VistaConversion(
            str(f.id), str(serie_id), f.file_name, nombre_nuevo, analisis.metodo,
            ruta.stat().st_size, analisis.estimado_salida, None,
            max(analisis.estimado_salida, 1), True, None,
            "Se puede convertir. El original se aparta y se puede deshacer.",
            advertencia=aviso, forzable=aviso is not None, token=token)

    async def _leer(self, serie_id: UUID, file_id: UUID) -> File | None:
        return (await self._db.execute(
            select(File).join(Issue, File.issue_id == Issue.id)
            .where(File.id == file_id, Issue.series_id == serie_id)
            .execution_options(populate_existing=True))).scalar_one_or_none()

    # ── conversión ──────────────────────────────────────────────────────────
    async def confirmar(self, token: str, *, forzar_compartido: bool = False) -> ResultadoConversion:
        firmada = verificar_token_conversion(token, self._secret, ahora=self._ahora,
                                             ignorar_caducidad=True)
        if firmada is None:
            raise TokenInvalidoError("La vista previa no es válida: vuelve a abrirla.")
        if firmada.accion != "convertir":
            raise TokenInvalidoError("Esa propuesta no es una conversión.")
        if verificar_token_conversion(token, self._secret, ahora=self._ahora) is None:
            raise TokenCaducadoError("La vista previa caducó; no se ha tocado nada.",
                                     puede_haberse_aplicado=False)
        f = await self._db.get(File, UUID(firmada.file_id), populate_existing=True)
        if f is None:
            return _conflicto(MotivoConversion.ARCHIVO_AUSENTE)
        previo = self._estado_meta(f)
        if previo and previo.get("estado") == "convertida":
            r = ResultadoConversion(_VERSION, "conversion", firmada.operacion, str(f.id),
                                    "ya_convertida", None, "Ya estaba convertida.", repetida=True,
                                    fecha=previo.get("fecha"))
            return r
        if f.file_format is not FileFormat.CBR:
            return _conflicto(MotivoConversion.NO_ES_CBR)
        if Path(firmada.ruta) != Path(f.file_path):
            return _conflicto(MotivoConversion.PROPUESTA_DESACTUALIZADA)
        ruta = Path(f.file_path)
        try:
            st = ruta.stat()
        except OSError:
            return _conflicto(MotivoConversion.ARCHIVO_AUSENTE)
        if (st.st_size, st.st_mtime_ns) != (firmada.tamano, firmada.mtime_ns) or \
                (f.sha256_hash and f.sha256_hash != firmada.sha256):
            return _conflicto(MotivoConversion.PROPUESTA_DESACTUALIZADA)
        return await self._ejecutar(f, firmada, forzar_compartido=forzar_compartido)

    async def _ejecutar(self, f: File, firmada: ConversionFirmada, *, forzar_compartido: bool) -> ResultadoConversion:
        ruta = Path(f.file_path)
        shared = await self._compartida(ruta)
        aviso = self._aviso(shared)
        if aviso and not forzar_compartido:
            return ResultadoConversion(_VERSION, "conversion", firmada.operacion, str(f.id),
                                       "omitida", shared.estado.value, aviso,
                                       advertencia=aviso)
        libre = True
        with contextlib.suppress(Exception):  # FakeSession sin Postgres
            libre = bool((await self._db.execute(
                text("SELECT pg_try_advisory_xact_lock(:c, :o)"),
                {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})).scalar())
        if libre is False:
            return _conflicto(MotivoConversion.CONFLICTO_DE_BLOQUEO)
        await bloquear_archivo(self._db, f.id)
        async with self._lock_bytes(f.id):
            f = (await self._db.execute(
                select(File).where(File.id == f.id).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if f is None:
                return _conflicto(MotivoConversion.ARCHIVO_AUSENTE)
            ruta = Path(f.file_path)
            shared = await self._compartida(ruta)
            if shared.bloquea and not forzar_compartido:
                return ResultadoConversion(_VERSION, "conversion", firmada.operacion, str(f.id),
                                           "omitida", shared.estado.value, self._aviso(shared) or "",
                                           advertencia=self._aviso(shared))
            try:
                analisis = await asyncio.to_thread(analizar, ruta, lector=self._lector)
            except ConversionBloqueadaError as exc:
                return _conflicto(exc.motivo, exc.mensaje)
            destino = ruta.with_suffix(".cbz")
            if destino.exists() and destino != ruta:
                return _conflicto(MotivoConversion.YA_EXISTE_CBZ)
            cuarentena = _cuarentena(self._settings) / str(f.id) / firmada.operacion
            try:
                comprobar_espacio(destino.parent, max(analisis.estimado_salida, 1), "conversión")
            except EspacioInsuficienteError as exc:
                return _conflicto(MotivoConversion.SIN_ESPACIO, str(exc))
            try:
                if analisis.metodo == "renombrar_zip":
                    os.replace(ruta, destino)
                    _fsync_dir(destino.parent)
                    nuevo_sha = firmada.sha256
                    nuevo_tamano = destino.stat().st_size
                else:
                    cuarentena.parent.mkdir(parents=True, exist_ok=True)
                    if os.stat(destino.parent).st_dev != os.stat(cuarentena.parent).st_dev:
                        return _conflicto(MotivoConversion.OTRO_DISCO)
                    fd, temporal = tempfile.mkstemp(prefix=f".{destino.name}.", suffix=".tmp",
                                                    dir=str(destino.parent))
                    os.close(fd)
                    tmp = Path(temporal)
                    try:
                        construccion = await asyncio.to_thread(
                            construir_cbz, ruta, tmp, lector=self._lector)
                        with tmp.open("rb") as fh:
                            os.fsync(fh.fileno())
                        nueva = await self._compartida(ruta)
                        if nueva.bloquea and not forzar_compartido:
                            tmp.unlink(missing_ok=True)
                            return ResultadoConversion(
                                _VERSION, "conversion", firmada.operacion, str(f.id),
                                "omitida", nueva.estado.value, self._aviso(nueva) or "",
                                advertencia=self._aviso(nueva))
                        os.replace(tmp, destino)
                        _fsync_dir(destino.parent)
                        nuevo_sha = construccion.sha256
                        nuevo_tamano = destino.stat().st_size
                    finally:
                        tmp.unlink(missing_ok=True)
                    cuarentena.mkdir(parents=True, exist_ok=True)
                    os.replace(ruta, cuarentena / ruta.name)
                    _fsync_dir(cuarentena)
                    _fsync_dir(ruta.parent)
                    self._diario_escribir(f, firmada, "original_apartado", cuarentena / ruta.name)
                self._diario_escribir(f, firmada, "publicado", destino)
                original_ruta = (ruta.with_suffix(".cbr") if analisis.metodo == "renombrar_zip"
                                 else cuarentena / ruta.name)
                self._actualizar_fila(f, firmada, ruta, destino, nuevo_sha, nuevo_tamano,
                                      metodo=analisis.metodo, original_ruta=original_ruta)
                try:
                    await self._db.commit()
                except Exception as exc:  # noqa: BLE001
                    raise ResultadoInciertoError(
                        "El CBZ se publicó pero no se pudo confirmar la fila.") from exc
            except (OSError, ConversionBloqueadaError) as exc:
                with contextlib.suppress(Exception):
                    await self._db.rollback()
                if isinstance(exc, ConversionBloqueadaError):
                    return _conflicto(exc.motivo, exc.mensaje)
                return _conflicto(MotivoConversion.ILEGIBLE, "No se pudo publicar el CBZ; no se ha tocado nada.")
        return ResultadoConversion(
            _VERSION, "conversion", firmada.operacion, str(f.id), "convertida", None,
            "Convertida a CBZ. El original está apartado y puedes deshacerlo.",
            advertencia=aviso, forzado_compartido=bool(aviso and forzar_compartido),
            metodo=analisis.metodo,
            antes={"ruta": str(ruta), "sha256": firmada.sha256, "tamano": firmada.tamano},
            despues={"ruta": str(destino), "sha256": nuevo_sha, "tamano": nuevo_tamano},
            fecha=_ahora_iso())

    @contextlib.asynccontextmanager
    async def _lock_bytes(self, file_id):
        bind = getattr(self._db, "bind", None)
        if bind is None:
            yield
            return
        async with bloqueo_de_fichero(motor_de(self._db), file_id):
            yield

    def _actualizar_fila(self, f: File, firmada, ruta: Path, destino: Path, sha: str,
                         tamano: int, *, metodo: str, original_ruta: Path) -> None:
        meta = copy.deepcopy(f.metadata_ if isinstance(f.metadata_, dict) else {})
        conv = meta.get("conversion") if isinstance(meta.get("conversion"), dict) else {}
        hist = list(conv.get("historial") or [])
        hist.append({"fecha": _ahora_iso(), "operacion_id": firmada.operacion,
                     "accion": "convertida", "metodo": metodo})
        meta["conversion"] = {
            "version": 1, "estado": "convertida", "operacion_id": firmada.operacion,
            "metodo": metodo, "fecha": _ahora_iso(),
            "original": {"ruta": str(original_ruta), "nombre": original_ruta.name,
                         "sha256": firmada.sha256, "tamano": firmada.tamano},
            "nuevo": {"ruta": str(destino), "sha256": sha, "tamano": tamano},
            "historial": hist[-20:],
        }
        st = destino.stat()
        f.file_path = str(destino)
        f.file_name = destino.name
        f.file_format = FileFormat.CBZ
        f.file_size_bytes = tamano
        f.file_mtime_ns = st.st_mtime_ns
        f.sha256_hash = sha
        if f.original_sha256 is None:
            f.original_sha256 = firmada.sha256
        f.metadata_ = meta

    def _diario_escribir(self, f: File, firmada, estado: str, ruta: Path) -> None:
        try:
            base = _diario(self._settings) / str(f.id)
            base.mkdir(parents=True, exist_ok=True)
            (base / f"{firmada.operacion}.json").write_text(json.dumps({
                "version": 1, "file_id": str(f.id), "operacion_id": firmada.operacion,
                "estado": estado, "fecha": _ahora_iso(), "ruta": str(ruta),
            }, ensure_ascii=False), encoding="utf-8")
        except OSError:
            logger.warning("conversion.diario_no_escribible")

    # ── deshacer / vaciar ───────────────────────────────────────────────────
    async def previsualizar_deshacer(self, serie_id: UUID, file_id: UUID) -> VistaConversion:
        f = await self._leer(serie_id, file_id)
        if f is None:
            raise TokenInvalidoError("Ese archivo no existe o no pertenece a esta serie.")
        conv = self._estado_meta(f)
        if not conv or conv.get("estado") != "convertida":
            raise TokenInvalidoError("Ese archivo no tiene una conversión que deshacer.")
        original = conv.get("original") or {}
        destino = Path(f.file_path)
        if (not original.get("ruta") or not Path(original["ruta"]).exists()) and \
                conv.get("metodo") != "renombrar_zip":
            return _vista_bloqueada(f, MotivoConversion.ARCHIVO_AUSENTE,
                                    "El original apartado no está; no se puede deshacer.")
        token = self._token(f, operacion=conv.get("operacion_id", str(uuid.uuid4())),
                            metodo=conv.get("metodo", "recomprimir"), accion="deshacer")
        return VistaConversion(
            str(f.id), str(serie_id), destino.name, original.get("nombre", ""),
            conv.get("metodo", "recomprimir"), destino.stat().st_size,
            int(original.get("tamano") or 0), None, 0, True, None,
            "Se puede deshacer: el original vuelve a su sitio.", token=token)

    async def deshacer(self, token: str, *, forzar_compartido: bool = False) -> ResultadoConversion:
        firmada = verificar_token_conversion(token, self._secret, ahora=self._ahora,
                                             ignorar_caducidad=True)
        if firmada is None or firmada.accion != "deshacer":
            raise TokenInvalidoError("La propuesta de deshacer no es válida.")
        if verificar_token_conversion(token, self._secret, ahora=self._ahora) is None:
            raise TokenCaducadoError("La vista previa caducó; no se ha tocado nada.",
                                     puede_haberse_aplicado=False)
        f = await self._db.get(File, UUID(firmada.file_id), populate_existing=True)
        if f is None:
            return _conflicto(MotivoConversion.ARCHIVO_AUSENTE)
        conv = self._estado_meta(f)
        if not conv or conv.get("estado") == "deshecha":
            return ResultadoConversion(_VERSION, "conversion", firmada.operacion, str(f.id),
                                       "ya_revertida", None, "Ya estaba deshecha.", repetida=True)
        original = conv.get("original") or {}
        destino = Path(f.file_path)
        origen = Path(original.get("ruta", ""))
        if not destino.exists() or (conv.get("metodo") != "renombrar_zip" and not origen.exists()):
            return _conflicto(MotivoConversion.ARCHIVO_AUSENTE)
        shared = await self._compartida(destino)
        aviso = self._aviso(shared)
        if aviso and not forzar_compartido:
            return ResultadoConversion(_VERSION, "conversion", firmada.operacion, str(f.id),
                                       "omitida", shared.estado.value, aviso, advertencia=aviso)
        await bloquear_archivo(self._db, f.id)
        restaurar = destino.with_suffix(".cbr")
        apartado = _cuarentena(self._settings) / str(f.id) / firmada.operacion / "deshecho" / destino.name
        apartado.parent.mkdir(parents=True, exist_ok=True)
        try:
            if conv.get("metodo") == "renombrar_zip":
                os.replace(destino, restaurar)
            else:
                os.replace(origen, restaurar)
                os.replace(destino, apartado)
        except OSError:
            return _conflicto(MotivoConversion.ILEGIBLE, "No se pudo deshacer; revisa los archivos.")
        meta = copy.deepcopy(f.metadata_ if isinstance(f.metadata_, dict) else {})
        conv = meta.get("conversion") if isinstance(meta.get("conversion"), dict) else {}
        conv["estado"] = "deshecha"
        conv["deshecho_en"] = _ahora_iso()
        conv.setdefault("historial", []).append(
            {"fecha": _ahora_iso(), "operacion_id": firmada.operacion, "accion": "deshecha"})
        meta["conversion"] = conv
        f.file_path = str(restaurar)
        f.file_name = restaurar.name
        f.file_format = FileFormat.CBR
        f.file_size_bytes = int(original.get("tamano") or 0)
        with contextlib.suppress(OSError):
            f.file_mtime_ns = restaurar.stat().st_mtime_ns
        f.sha256_hash = original.get("sha256")
        f.metadata_ = meta
        try:
            await self._db.commit()
        except Exception as exc:  # noqa: BLE001
            raise ResultadoInciertoError("El original volvió pero no se pudo confirmar la fila.") from exc
        return ResultadoConversion(_VERSION, "conversion", firmada.operacion, str(f.id),
                                   "revertida", None, "Original restaurado; el CBZ queda apartado.",
                                   advertencia=aviso, forzado_compartido=bool(aviso and forzar_compartido),
                                   metodo=conv.get("metodo"), fecha=_ahora_iso())

    def vaciar_originales(self, lote: int = 50) -> int:
        """Borra, por tandas, los originales apartados más antiguos. Solo cuarentena."""
        base = _cuarentena(self._settings)
        if not base.exists():
            return 0
        borrados = 0
        for operacion in sorted(base.glob("*/*")):
            if borrados >= lote:
                break
            if operacion.is_dir():
                padre = operacion.parent
                shutil.rmtree(operacion, ignore_errors=True)
                with contextlib.suppress(OSError):
                    padre.rmdir()
                borrados += 1
        return borrados

    async def reconciliar(self, file_id: UUID) -> bool:
        """Repara la fila si el CBZ ya está publicado pero el commit quedó incierto."""
        f = await self._db.get(File, UUID(str(file_id)), populate_existing=True)
        if f is None:
            return False
        conv = self._estado_meta(f)
        if not conv or conv.get("estado") != "convertida":
            return False
        destino = Path(conv.get("nuevo", {}).get("ruta", ""))
        if not destino.exists():
            return False
        st = destino.stat()
        if f.file_path != str(destino) or f.sha256_hash != conv["nuevo"].get("sha256"):
            f.file_path, f.file_name = str(destino), destino.name
            f.file_format = FileFormat.CBZ
            f.sha256_hash = conv["nuevo"].get("sha256")
            f.file_size_bytes, f.file_mtime_ns = st.st_size, st.st_mtime_ns
            await self._db.commit()
            return True
        return False
