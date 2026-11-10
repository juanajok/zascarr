# ruff: noqa: E501
"""#480/BL-CNV3: ComicInfo desde la ficha, reutilizando el plan de B6.

La vista previa usa `TaggerService.planificar` (el mismo plan que B6) y firma un token con la
identidad del archivo y los campos exactos. «Guardar» envía solo ese token: se verifica stat/hash/
huella y se aplica **ese** plan, sin volver a planificar ni consultar red. El guardián #488 avisa y
pide confirmación; no bloquea en duro. Sin migración.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.comicinfo_write import Accion, CampoPlan, ComicInfoInvalidoError
from zascarr.models import File, FileFormat, Issue
from zascarr.services.compartidos import EstadoComparticion, estado_de_comparticion
from zascarr.services.tagger import (
    CADUCADO,
    ESCRITO,
    SALTADO,
    TaggerService,
    bloqueo_de_fichero,
    motor_de,
)
from zascarr.services.tokens_revision import crear_token, verificar_token
from zascarr.services.vinculacion import (
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
)
from zascarr.utils.bloqueo_archivo import bloquear_archivo

logger = structlog.get_logger()

PROPOSITO_COMICINFO = "comicinfo_ficha"
MAX_TOKEN_COMICINFO = 8192
_TTL = 15 * 60


@dataclass(frozen=True)
class VistaComicInfo:
    file_id: str
    serie_id: str
    nombre: str
    es_cbr: bool
    puede_aplicar: bool
    motivo: str | None
    mensaje: str
    campos: list[CampoPlan] = field(default_factory=list)
    advertencia: str | None = None
    forzable: bool = False
    token: str | None = None


@dataclass
class ResultadoComicInfo:
    version: int
    tipo: str
    operacion_id: str
    file_id: str
    resultado: Literal["guardado", "sin_cambios", "omitido", "caducado"]
    motivo: str | None
    mensaje: str
    campos: list[CampoPlan] = field(default_factory=list)
    advertencia: str | None = None
    forzado_compartido: bool = False


def _huella(campos: list[CampoPlan]) -> str:
    crudo = json.dumps([[c.tag, c.accion.value, c.actual, c.nuevo] for c in campos],
                       ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(crudo.encode()).hexdigest()


def _campos_para_token(campos: list[CampoPlan]) -> list[list[str | None]]:
    return [[c.tag, c.accion.value, c.actual, c.nuevo] for c in campos]


def _campos_desde_token(datos: list) -> list[CampoPlan] | None:
    if not isinstance(datos, list):
        return None
    campos: list[CampoPlan] = []
    try:
        for item in datos:
            if not isinstance(item, list) or len(item) != 4:
                return None
            tag, accion, actual, nuevo = item
            if not all(isinstance(v, (str, type(None))) for v in item):
                return None
            campos.append(CampoPlan(str(tag), Accion(str(accion)),
                                    actual if isinstance(actual, str) else None,
                                    nuevo if isinstance(nuevo, str) else None))
    except (ValueError, TypeError):
        return None
    return campos


def _sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with ruta.open("rb") as fh:
        for bloque in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _desactualizada(operacion: str, file_id: str, mensaje: str,
                    campos: list[CampoPlan] | None = None) -> ResultadoComicInfo:
    return ResultadoComicInfo(1, "comicinfo", operacion, file_id, "caducado",
                              "propuesta_desactualizada", mensaje, campos=campos or [])


class ComicInfoFichaService:
    def __init__(self, db: AsyncSession, *, secret: str | None = None, ahora: float | None = None):
        self._db = db
        self._secret = secret or get_settings().secret_key
        self._ahora = ahora
        self._tagger = TaggerService(db)

    async def _leer(self, serie_id: UUID, file_id: UUID) -> File | None:
        return (await self._db.execute(
            select(File).join(Issue, File.issue_id == Issue.id)
            .where(File.id == file_id, Issue.series_id == serie_id)
            .execution_options(populate_existing=True))).scalar_one_or_none()

    def _aviso(self, decision) -> str | None:
        if decision.estado is EstadoComparticion.NO_COMPARTIDO:
            return None
        return (f"Cuidado: este archivo parece compartido ({decision.causa}). "
                "Guardar el ComicInfo reescribe el CBZ y puede afectar a la siembra. "
                "Puedes continuar con la confirmación explícita.")

    async def previsualizar(self, serie_id: UUID, file_id: UUID) -> VistaComicInfo:
        f = await self._leer(serie_id, file_id)
        if f is None:
            raise TokenInvalidoError("Ese archivo no existe o no pertenece a esta serie.")
        if f.file_format is FileFormat.CBR:
            return VistaComicInfo(str(f.id), str(serie_id), f.file_name, True, False, "cbr",
                                  "Es un CBR: conviértelo primero a CBZ y luego podrás guardar su información.")
        if f.file_format is not FileFormat.CBZ:
            return VistaComicInfo(str(f.id), str(serie_id), f.file_name, False, False, "formato",
                                  "Solo se puede escribir ComicInfo en un CBZ.")
        if f.is_missing:
            return VistaComicInfo(str(f.id), str(serie_id), f.file_name, False, False, "ausente",
                                  "El archivo no está en el disco; no se puede escribir.")
        ruta = Path(f.file_path)
        try:
            st = ruta.stat()
            campos = await self._tagger.planificar(f)
        except OSError:
            return VistaComicInfo(str(f.id), str(serie_id), f.file_name, False, False, "ausente",
                                  "El archivo no está en el disco; no se puede escribir.")
        except ComicInfoInvalidoError as exc:
            return VistaComicInfo(str(f.id), str(serie_id), f.file_name, False, False, "invalido",
                                  f"El ComicInfo actual no se puede leer: {exc}")
        sha = f.sha256_hash or await asyncio.to_thread(_sha256, ruta)
        decision = await estado_de_comparticion(ruta)
        aviso = self._aviso(decision)
        operacion = str(uuid.uuid4())
        token = crear_token(PROPOSITO_COMICINFO, str(f.id), {
            "version": 1, "operacion": operacion, "ruta": str(ruta),
            "tamano": st.st_size, "mtime_ns": st.st_mtime_ns, "sha256": sha,
            "huella": _huella(campos),
        }, self._secret, ahora=self._ahora, ttl=_TTL)
        return VistaComicInfo(
            str(f.id), str(serie_id), f.file_name, False, True, None,
            "Revisa los cambios y guarda para escribir el ComicInfo." if campos
            else "El ComicInfo ya coincide con lo que sabe ZascArr; no hay nada que escribir.",
            campos=campos, advertencia=aviso, forzable=aviso is not None, token=token)

    async def aplicar(self, token: str, *, forzar_compartido: bool = False,
                      file_id_esperado: str | UUID | None = None,
                      serie_id_esperado: str | UUID | None = None) -> ResultadoComicInfo:
        if file_id_esperado is None:
            raise TokenInvalidoError("Falta el archivo de la propuesta.")
        datos = verificar_token(token, PROPOSITO_COMICINFO, str(file_id_esperado), self._secret,
                                ahora=self._ahora)
        if datos is None:
            raise TokenCaducadoError("La vista previa caducó o no es válida; no se ha escrito nada.",
                                     puede_haberse_aplicado=False)
        if not isinstance(datos.get("huella"), str) or len(datos["huella"]) != 64:
            raise TokenInvalidoError("El plan firmado no es válido; no se ha escrito nada.")
        operacion = str(datos.get("operacion", ""))
        campos: list[CampoPlan] = []
        f = await self._db.get(File, UUID(str(file_id_esperado)), populate_existing=True)
        if f is None:
            raise TokenInvalidoError("Ese archivo ya no existe.")
        if serie_id_esperado is not None and await self._leer(
                UUID(str(serie_id_esperado)), UUID(str(file_id_esperado))) is None:
            return _desactualizada(operacion, str(f.id),
                                   "El archivo ya no pertenece a esta serie; no se ha escrito nada.")
        if f.file_format is not FileFormat.CBZ:
            return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "omitido", "formato",
                                      "Solo se puede escribir ComicInfo en un CBZ.")
        ruta = Path(f.file_path)
        try:
            st = ruta.stat()
        except OSError:
            return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "omitido", "ausente",
                                      "El archivo no está en el disco.")
        shared = await estado_de_comparticion(ruta)
        aviso = self._aviso(shared)
        if aviso and not forzar_compartido:
            return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "omitido",
                                      shared.estado.value, aviso, campos=campos, advertencia=aviso)
        await bloquear_archivo(self._db, f.id)
        lock = (bloqueo_de_fichero(motor_de(self._db), f.id)
                if getattr(self._db, "bind", None) is not None else contextlib.nullcontext())
        async with lock:
            f = (await self._db.execute(
                select(File).where(File.id == f.id).with_for_update()
                .execution_options(populate_existing=True))).scalar_one_or_none()
            if f is None:
                return ResultadoComicInfo(1, "comicinfo", operacion, "", "omitido", "ausente",
                                          "Ese archivo ya no existe.")
            ruta = Path(f.file_path)
            try:
                st = ruta.stat()
            except OSError:
                return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "omitido",
                                          "ausente", "El archivo no está en el disco.")
            if (str(ruta), st.st_size, st.st_mtime_ns) != (
                    datos.get("ruta"), datos.get("tamano"), datos.get("mtime_ns")) or \
                    await asyncio.to_thread(_sha256, ruta) != datos.get("sha256"):
                return _desactualizada(operacion, str(f.id),
                                       "El archivo cambió desde la vista previa; no se ha escrito nada.")
            # #583: la fila fresca tiene que seguir siendo el MISMO CBZ en la MISMA serie.
            if f.file_format is not FileFormat.CBZ or f.is_missing or f.issue_id is None:
                return _desactualizada(operacion, str(f.id),
                                       "El archivo o su relación cambiaron; no se ha escrito nada.")
            if serie_id_esperado is not None and await self._leer(
                    UUID(str(serie_id_esperado)), UUID(str(f.id))) is None:
                return _desactualizada(operacion, str(f.id),
                                       "El archivo ya no pertenece a esta serie; no se ha escrito nada.")
            try:
                campos = await self._tagger.planificar(f)
            except ComicInfoInvalidoError:
                return _desactualizada(operacion, str(f.id),
                                       "El ComicInfo cambió desde la vista previa; no se ha escrito nada.")
            # #583/#586: el plan firmado es una huella, no una copia del texto. Si cambió
            # un locked_field o cualquier dato de la ficha, la huella no coincide. Si
            # coincide, se aplica el plan FRESCO (idéntico al firmado) sin volver a leer red.
            if _huella(campos) != datos.get("huella"):
                return _desactualizada(operacion, str(f.id),
                                       "La información del número cambió desde la vista previa; no se ha escrito nada.")
            shared = await estado_de_comparticion(ruta)
            aviso = self._aviso(shared)
            if shared.bloquea and not forzar_compartido:
                return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "omitido",
                                          shared.estado.value, aviso or "", campos=campos,
                                          advertencia=aviso)
            resultado = await self._tagger.aplicar_plan(
                f, campos, estado_antes=(st.st_size, st.st_mtime_ns))
        if resultado.accion == SALTADO:
            return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "sin_cambios", None,
                                      resultado.motivo or "Sin cambios.", campos=campos,
                                      advertencia=aviso)
        if resultado.accion == CADUCADO:
            return _desactualizada(operacion, str(f.id),
                                   resultado.motivo or "Plan caducado; no se ha escrito nada.",
                                   campos)
        if resultado.accion != ESCRITO:
            return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "omitido",
                                      resultado.accion, resultado.motivo or "No se escribió.",
                                      campos=campos)
        try:
            await self._db.commit()
        except Exception as exc:  # noqa: BLE001
            raise ResultadoInciertoError("El XML se escribió pero no se pudo confirmar la fila.") from exc
        return ResultadoComicInfo(1, "comicinfo", operacion, str(f.id), "guardado", None,
                                  "ComicInfo guardado en el tebeo.", campos=campos,
                                  advertencia=aviso,
                                  forzado_compartido=bool(aviso and forzar_compartido))
