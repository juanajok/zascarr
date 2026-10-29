# ruff: noqa: E501
"""#332 residual 4 — aceptación explícita de una adopción inicial con N ilegibles.

Contrato de producto (memo v1.0):
  · Solo una adopción inicial (`kind="adoption"`) terminada, sin errores y con `unreadable=N>0`.
  · La oferta y el aviso salen del informe persistido, nunca del estado en memoria.
  · El marcador y el registro se escriben juntos, en un único UPDATE condicional.
  · El informe de adopción NO se muta: la aceptación se guarda como evidencia en una fila
    `ImportRun kind="adoption_acceptance"`.
  · La lectura es estricta: el marcador solo vale `is True` y el registro se valida entero.
  · El incremental sigue conservador: esta aceptación no lo autoriza cuando vuelve a haber ilegibles.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import ImportRun
from zascarr.services.registro_biblioteca import CLAVE_CERROJO_REGISTRO
from zascarr.services.runtime_settings import RuntimeSettingsService

logger = structlog.get_logger()

#: Claves internas de `runtime_settings` (misma fila JSONB; nunca editables desde Ajustes).
CLAVE_MARCADOR = "_library_adoption_done"
CLAVE_ACEPTACION = "_library_adoption_unreadable_accepted"

#: Cota de entrada: el recuento es un contador de carpetas/archivos, no un número libre.
MAX_ILEGIBLES = 1_000_000


@dataclass(frozen=True)
class Aceptacion:
    """Registro estructurado de una aceptación, ya validado."""

    count: int
    accepted_at: datetime
    run_id: UUID
    auth_mode: str


def parsear_aceptacion(valor: object) -> Aceptacion | None:
    """Lee el registro con tipos estrictos. Cualquier desviación es «no autoriza».

    `bool` es subclase de `int`: se rechaza explícitamente para que `true` no cuente como 1.
    La fecha debe traer zona (se guarda en UTC con offset) y el `run_id` debe ser un UUID.
    """
    if not isinstance(valor, dict):
        return None
    count = valor.get("count")
    if type(count) is not int or not 1 <= count <= MAX_ILEGIBLES:
        return None
    accepted_at = valor.get("accepted_at")
    if not isinstance(accepted_at, str):
        return None
    try:
        fecha = datetime.fromisoformat(accepted_at)
    except ValueError:
        return None
    if fecha.tzinfo is None:
        return None
    run_id = valor.get("run_id")
    try:
        identificador = UUID(str(run_id))
    except (ValueError, TypeError, AttributeError):
        return None
    auth_mode = valor.get("auth_mode")
    if not isinstance(auth_mode, str) or not auth_mode:
        return None
    return Aceptacion(count=count, accepted_at=fecha.astimezone(UTC),
                      run_id=identificador, auth_mode=auth_mode)


def _entero_no_negativo(valor: object) -> int:
    """Los informes viejos pueden no traer las claves de lotes; se tratan como 0."""
    if type(valor) is int and valor >= 0:
        return valor
    return 0


@dataclass(frozen=True)
class ResultadoAceptacion:
    """Resultado estable para la UI y para los clientes que no usan HTMX."""

    status: int
    reason: str
    aceptacion: Aceptacion | None = None

    @property
    def ok(self) -> bool:
        return self.status == 200


@dataclass(frozen=True)
class Evaluacion:
    """Lo que la pantalla necesita: oferta, aviso permanente y estado corrupto."""

    ultima: ImportRun | None = None
    oferta: bool = False
    unreadable: int = 0
    aceptacion: Aceptacion | None = None
    aviso: str | None = None

    @property
    def run_id(self) -> str | None:
        return str(self.ultima.id) if self.ultima is not None else None


def _unreadable_de(run: ImportRun | None) -> int:
    if run is None:
        return 0
    valor = (run.details or {}).get("unreadable")
    return valor if type(valor) is int and valor > 0 else 0


async def _ultima_adopcion(db: AsyncSession) -> ImportRun | None:
    """El último informe de adopción, desempatado por id (el cerrojo impide solapes reales)."""
    return (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == "adoption")
        .order_by(ImportRun.started_at.desc(), ImportRun.id.desc())
        .limit(1)
    )).scalar_one_or_none()


async def evaluar(db: AsyncSession, *, en_marcha: bool = False) -> Evaluacion:
    """Deriva oferta y aviso del almacén persistente, sin mirar el estado en memoria."""
    valores = await RuntimeSettingsService(db).get_overrides()
    ultima = await _ultima_adopcion(db)
    tiene_marcador = CLAVE_MARCADOR in valores
    marcador = valores.get(CLAVE_MARCADOR)
    tiene_registro = CLAVE_ACEPTACION in valores
    aceptacion = parsear_aceptacion(valores.get(CLAVE_ACEPTACION)) if tiene_registro else None
    unreadable = _unreadable_de(ultima)

    aviso: str | None = None
    oferta = False
    if tiene_marcador and marcador is not True:
        aviso = ("El marcador de adopción guardado no es válido. No se autoriza ninguna aceptación "
                 "y no se borra nada.")
    elif marcador is True:
        if tiene_registro and aceptacion is None:
            aviso = ("La aceptación guardada no se puede verificar. No se autoriza nada y no se "
                     "borra nada.")
    elif tiene_registro:
        aviso = ("Hay una aceptación guardada sin marcador. No se autoriza nada; revisa el estado "
                 "antes de continuar.")
    elif not en_marcha and ultima is not None and validar_informe(ultima, ultima.id, unreadable) is None:
        oferta = True

    return Evaluacion(ultima=ultima, oferta=oferta, unreadable=unreadable,
                      aceptacion=aceptacion, aviso=aviso)


@asynccontextmanager
async def _cerrojo_de_registro(db: AsyncSession, espera_maxima: float = 2.0):
    """Toma el mismo cerrojo consultivo que el registro de la biblioteca.

    Si está ocupado, espera un poco: dos aceptaciones simultáneas deben acabar en idempotencia,
    no en un 409. Un registro en marcha lo retiene minutos, así que agotada la espera se rechaza.
    """
    if not isinstance(db, AsyncSession) or db.bind is None:
        yield True
        return
    conexion = await db.bind.connect()
    obtenido = False
    try:
        limite = time.monotonic() + espera_maxima
        while True:
            obtenido = bool((await conexion.execute(
                text("SELECT pg_try_advisory_lock(:k)"),
                {"k": CLAVE_CERROJO_REGISTRO})).scalar())
            if obtenido:
                break
            if time.monotonic() >= limite:
                yield False
                return
            await asyncio.sleep(0.05)
        yield True
    finally:
        if obtenido:
            with contextlib.suppress(Exception):
                await conexion.execute(text("SELECT pg_advisory_unlock(:k)"),
                                       {"k": CLAVE_CERROJO_REGISTRO})
        await conexion.close()


def _log(run_id: UUID, count: int, auth_mode: str, resultado: ResultadoAceptacion) -> None:
    logger.info("library_adopter.acceptance", run_id=str(run_id), count=count,
                auth_mode=auth_mode, result=resultado.reason)


async def _resultado(db: AsyncSession, run_id: UUID, count: int, status: int, reason: str,
                     *, aceptacion: Aceptacion | None = None) -> ResultadoAceptacion:
    resultado = ResultadoAceptacion(status=status, reason=reason, aceptacion=aceptacion)
    _log(run_id, count, get_settings().auth_mode, resultado)
    return resultado


async def _leer_marcador(db: AsyncSession) -> tuple[dict, object, bool, Aceptacion | None]:
    valores = await RuntimeSettingsService(db).get_overrides()
    tiene = CLAVE_MARCADOR in valores
    registro = valores.get(CLAVE_ACEPTACION)
    return valores, valores.get(CLAVE_MARCADOR), tiene, parsear_aceptacion(registro)


async def _reread_tras_carrera(db: AsyncSession, run_id: UUID, count: int) -> ResultadoAceptacion:
    valores, marcador, tiene, aceptacion = await _leer_marcador(db)
    if tiene and marcador is True:
        if CLAVE_ACEPTACION in valores and aceptacion is None:
            return await _resultado(db, run_id, count, 409, "corrupt_record")
        if aceptacion is not None and aceptacion.run_id == run_id and aceptacion.count == count:
            return await _resultado(db, run_id, count, 200, "already_accepted_idempotent",
                                    aceptacion=aceptacion)
        return await _resultado(db, run_id, count, 409, "already_accepted")
    if tiene:
        return await _resultado(db, run_id, count, 409, "corrupt_flag")
    return await _resultado(db, run_id, count, 409, "already_accepted")


async def aceptar(db: AsyncSession, run_id: UUID, count: int, *, en_marcha: bool = False,
                  espera_cerrojo: float = 2.0) -> ResultadoAceptacion:
    """Acepta una adopción inicial con N ilegibles, de forma explícita y atómica."""
    if type(count) is not int or not 1 <= count <= MAX_ILEGIBLES:
        return ResultadoAceptacion(status=422, reason="invalid_payload")
    if en_marcha:
        return await _resultado(db, run_id, count, 409, "in_progress")

    async with _cerrojo_de_registro(db, espera_cerrojo) as libre:
        if not libre:
            return await _resultado(db, run_id, count, 409, "in_progress")

        _valores, marcador, tiene_marcador, aceptacion = await _leer_marcador(db)
        if tiene_marcador and marcador is not True:
            return await _resultado(db, run_id, count, 409, "corrupt_flag")
        if tiene_marcador and marcador is True:
            if CLAVE_ACEPTACION in _valores and aceptacion is None:
                return await _resultado(db, run_id, count, 409, "corrupt_record")
            if aceptacion is not None and aceptacion.run_id == run_id and aceptacion.count == count:
                return await _resultado(db, run_id, count, 200, "already_accepted_idempotent",
                                        aceptacion=aceptacion)
            return await _resultado(db, run_id, count, 409, "already_accepted")

        ultima = await _ultima_adopcion(db)
        run = await db.get(ImportRun, run_id)
        motivo = validar_informe(run, ultima.id if ultima is not None else run_id, count)
        if motivo is not None:
            return await _resultado(db, run_id, count, 404 if motivo == "not_found" else 409, motivo)

        ahora = datetime.now(UTC)
        iso = ahora.isoformat()
        auth_mode = get_settings().auth_mode
        patch = {
            CLAVE_MARCADOR: True,
            CLAVE_ACEPTACION: {
                "count": count,
                "accepted_at": iso,
                "run_id": str(run_id),
                "auth_mode": auth_mode,
            },
        }
        fila = (await db.execute(text(
            'UPDATE runtime_settings '
            'SET "values" = COALESCE("values", \'{}\'::jsonb) || CAST(:patch AS jsonb) '
            'WHERE id = 1 AND NOT (COALESCE("values", \'{}\'::jsonb) ? :clave) '
            'RETURNING id'
        ), {"patch": json.dumps(patch, ensure_ascii=False), "clave": CLAVE_MARCADOR})).scalar()
        if fila is None:
            return await _reread_tras_carrera(db, run_id, count)

        db.add(ImportRun(
            started_at=ahora, finished_at=ahora,
            details={
                "kind": "adoption_acceptance",
                "adoption_run_id": str(run_id),
                "count": count,
                "auth_mode": auth_mode,
                "accepted_at": iso,
            },
        ))
        await db.commit()
        return await _resultado(db, run_id, count, 200, "accepted",
                                aceptacion=Aceptacion(count=count, accepted_at=ahora,
                                                      run_id=run_id, auth_mode=auth_mode))


def validar_informe(run: ImportRun | None, ultimo_id: UUID, count: int) -> str | None:
    """Devuelve el motivo de rechazo (string estable) o `None` si el informe es aceptable.

    El orden importa: primero el tipo de informe (un incremental no puede «robar» la adopción),
    después la vigencia, el cierre, los errores y, por último, el recuento.
    """
    if run is None:
        return "not_found"
    detalles = dict(run.details or {})
    if detalles.get("kind") != "adoption":
        return "incremental_run"
    if run.finished_at is None:
        return "not_terminated"
    if run.id != ultimo_id:
        return "stale_run"
    if run.error_count or detalles.get("errors"):
        return "has_errors"
    unreadable = detalles.get("unreadable")
    if type(unreadable) is not int or unreadable <= 0:
        return "zero_unreadable"
    if unreadable != count:
        return "count_mismatch"
    if _entero_no_negativo(detalles.get("reverted")) or _entero_no_negativo(detalles.get("unknown")):
        return "batch_unverified"
    return None
