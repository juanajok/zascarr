# ruff: noqa: E501

"""Rescan de la biblioteca a petición y periódico (#BL-R9).

Una sola operación de disco a la vez: el rescan comparte el cerrojo consultivo de ciclo `(326, 2)`
con el ciclo del importador (`comprobacion_disco`), de modo que nunca coinciden dos paseos de la
biblioteca. El estado de la ejecución vive en memoria (proceso único, un solo worker); el resultado
duradero es el `ImportRun` con `details["kind"] = "rescan"` que escribe `LibraryAdopter.rescanear`
(la lectura de #231 excluye los informes con `kind`, así que no se confunde con «el último ciclo»).

El disparador manual corre la operación entera (nuevos + cambiados + desaparecidos); el automático
es el mismo camino, se salta si hay una manual en curso o si el cerrojo está ocupado, y consta en
el log. El registro incremental (#326) sigue siendo manual y NO pasa por aquí.
"""
from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import ImportRun
from zascarr.services import tareas
from zascarr.services.comprobacion_disco import CLAVE_CERROJO_CICLO
from zascarr.services.library_adopter import LibraryAdopter, RescanReport

logger = structlog.get_logger()

DISPARADOR_MANUAL = "manual"
DISPARADOR_AUTOMATICO = "automatico"


class FaseRescan(StrEnum):
    INACTIVO = "inactivo"
    CORRIENDO = "corriendo"
    TERMINADO = "terminado"
    ERROR = "error"
    OCUPADO = "ocupado"


@dataclass
class EstadoRescan:
    fase: FaseRescan = FaseRescan.INACTIVO
    iniciado: datetime | None = None
    terminado: datetime | None = None
    run_id: str | None = None
    disparador: str | None = None
    causa: str | None = None               # solo el TIPO de excepción; nunca mensaje ni ruta
    informe: RescanReport | None = None    # el último informe (en memoria; el duradero es el ImportRun)
    foco_resultado: bool = False           # el siguiente fragmento debe enfocar el resultado una vez

    @property
    def en_curso(self) -> bool:
        return self.fase is FaseRescan.CORRIENDO


_estado = EstadoRescan()
_tarea: asyncio.Task | None = None


def estado_actual() -> EstadoRescan:
    return _estado


# ── Resumen del informe y último rescan persistido (comparten Auditoría y Biblioteca) ──

CAMPOS_RESUMEN = (
    "files_scanned", "sin_cambios", "ya_registrados", "nuevos_entregados",
    "nuevos_registrados", "nuevos_a_revisar", "repetidos", "reenlazados",
    "re_triados", "re_triados_igual", "re_triados_cambiado",
    "re_triados_a_revisar", "re_triados_descartado", "copias_de_otra",
    "re_triados_protegidos", "discrepancias_registradas",
    "desaparecidos", "reaparecidos", "errores", "omitidos", "ambiguos",
    "no_revisado", "unreadable", "por_comprobar", "resultado_biblioteca",
)


def resumen_de(informe) -> dict | None:
    """Normaliza el informe —en memoria (`RescanReport`) o persistido (dict de `ultimo_persistido`)—
    a un dict para la plantilla. Un informe persistido debe pintarse igual que uno en memoria:
    tras un reinicio del proceso el estado en memoria ya no existe y la pantalla lee el `ImportRun`."""
    if informe is None:
        return None
    fuente = informe.get if isinstance(informe, dict) else (lambda c: getattr(informe, c, None))
    out: dict = {}
    for c in CAMPOS_RESUMEN:
        v = fuente(c)
        if c in ("errores", "omitidos", "ambiguos") or isinstance(v, (list, tuple)):
            out[c] = list(v) if v else []
        elif isinstance(v, bool):
            out[c] = v
        elif isinstance(v, (int, float)):
            out[c] = v or 0
        else:
            out[c] = v or ""
    out["disparador"] = fuente("disparador") or "manual"
    out["started_at"] = fuente("started_at")
    return out


async def ultimo_persistido(db: AsyncSession) -> dict | None:
    """El último rescan persistido (`kind="rescan"`), para una página recién cargada."""
    run = (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == "rescan")
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if not run:
        return None
    detalles = dict(run.details or {})
    detalles["started_at"] = run.started_at
    detalles["files_scanned"] = run.files_scanned
    detalles["errores"] = detalles.get("errores") or []
    return detalles


# ── Cuándo toca el siguiente (#1160): se cuenta desde el último rescan, no desde el arranque ──

#: Cadencias que ofrece Ajustes, en minutos: apagada, una vez al día, una vez a la semana.
INTERVALOS_AJUSTES = (0, 1440, 10080)
#: Tras un turno saltado (otra operación de disco en marcha) o fallido, no se reintenta antes.
REINTENTO_TRAS_SALTO = 1800

_arranque: datetime = datetime.now(UTC)
_ultima: datetime | None = None


def ultima_ejecucion() -> datetime | None:
    """Cuándo empezó el último rescan terminado (de este proceso o leído del `ImportRun`)."""
    return _ultima


def anotar_ultima(cuando: datetime | None) -> None:
    """Recuerda el último rescan; nunca retrocede."""
    global _ultima
    if cuando is not None and (_ultima is None or cuando > _ultima):
        _ultima = cuando


async def cargar_ultima_persistida(fabrica) -> None:
    """Una sola lectura al arrancar: sin ella cada reinicio (cada despliegue) reiniciaría la cuenta."""
    async with fabrica() as db:
        ultimo = await ultimo_persistido(db)
    if ultimo is not None:
        anotar_ultima(ultimo.get("started_at"))


def proxima_ejecucion(minutos: int) -> datetime | None:
    """Cuándo toca el periódico con esa cadencia; `None` si está apagado.

    Se cuenta desde el último rescan; si nunca hubo, desde el arranque del proceso. Puede quedar
    en el pasado (vencida: toca en cuanto el bucle despierte)."""
    if minutos <= 0:
        return None
    base = _ultima or _arranque
    return base.replace(tzinfo=base.tzinfo or UTC) + timedelta(minutes=minutos)


def consumir_foco_resultado() -> bool:
    """Devuelve True una sola vez, en el primer fragmento que ve el resultado."""
    if not _estado.foco_resultado:
        return False
    _estado.foco_resultado = False
    return True


@asynccontextmanager
async def _cerrojo_ciclo(fabrica):
    """El mismo cerrojo consultivo de sesión que el ciclo del importador (`CLAVE_CERROJO_CICLO`):
    un solo paseo de disco en marcha entre los dos. `try` sin espera; si no se obtiene, el turno
    se salta (el otro termina y el siguiente turno reintenta)."""
    async with fabrica() as sesion:
        if getattr(sesion, "bind", None) is None:
            yield True
            return
        conexion = await sesion.bind.connect()
        obtenido = False
        try:
            obtenido = bool((await conexion.execute(
                text("SELECT pg_try_advisory_lock(:c, :o)"),
                {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})).scalar())
            yield obtenido
        finally:
            try:
                if obtenido:
                    await conexion.execute(
                        text("SELECT pg_advisory_unlock(:c, :o)"),
                        {"c": CLAVE_CERROJO_CICLO[0], "o": CLAVE_CERROJO_CICLO[1]})
                await conexion.close()
            except Exception:  # noqa: BLE001 — una conexión rota no vuelve al pool con el lock
                with contextlib.suppress(Exception):
                    await conexion.invalidate()


async def _correr(fabrica, disparador: str) -> RescanReport:
    async with fabrica() as sesion:
        return await LibraryAdopter(sesion).rescanear(disparador=disparador)


async def _ejecutar_tarea(fabrica, disparador: str) -> None:
    tarea = tareas.iniciar("rescanear", enlace="/ui/auditoria#rescan-biblioteca",
                           origen=f"rescan:{disparador}")
    try:
        await _ejecutar_tarea_con_cerrojo(fabrica, disparador, tarea)
    finally:
        if tarea is not None and tarea.estado.value == "en_curso":
            tareas.terminar(tarea.id, resumen="Biblioteca actualizada")


async def _ejecutar_tarea_con_cerrojo(fabrica, disparador: str, tarea) -> None:
    async with _cerrojo_ciclo(fabrica) as libre:
        if not libre:
            _estado.fase = FaseRescan.OCUPADO
            _estado.terminado = datetime.now(UTC)
            logger.info("rescan.ocupado", disparador=disparador)
            if tarea is not None:
                # No es un fallo: otra operación de disco tenía el cerrojo y no se lanzó nada.
                tareas.terminar(tarea.id, resumen="Otra operación de disco estaba en marcha")
            return
        try:
            informe = await _correr(fabrica, disparador)
            _estado.informe = informe
            _estado.fase = FaseRescan.TERMINADO
            _estado.run_id = str(informe.run_id) if informe.run_id else None
            _estado.foco_resultado = True
            anotar_ultima(informe.started_at)
            logger.info(
                "rescan.terminado", disparador=disparador,
                run_id=_estado.run_id,
                revisados=informe.files_scanned,
                nuevos=informe.nuevos_registrados + informe.nuevos_a_revisar,
                re_triados=informe.re_triados,
                desaparecidos=informe.desaparecidos,
                duracion_ms=int((informe.finished_at - informe.started_at).total_seconds() * 1000)
                if informe.finished_at and informe.started_at else None)
        except asyncio.CancelledError:
            if tarea is not None:
                tareas.error(tarea.id, tipo_error="CancelledError")
            _estado.fase = FaseRescan.INACTIVO
            _estado.causa = "CancelledError"
            raise
        except Exception as exc:  # noqa: BLE001 — el estado no propaga detalle técnico
            if tarea is not None:
                tareas.error(tarea.id, tipo_error=type(exc).__name__)
            _estado.fase = FaseRescan.ERROR
            _estado.causa = type(exc).__name__
            logger.warning("rescan.fallido", disparador=disparador, error=type(exc).__name__)
        finally:
            _estado.terminado = datetime.now(UTC)


def iniciar_manual(fabrica) -> bool:
    """Marca «en curso» y crea la tarea. Devuelve False si ya había una."""
    global _estado, _tarea
    if _estado.en_curso:
        return False
    _estado = EstadoRescan(fase=FaseRescan.CORRIENDO, iniciado=datetime.now(UTC),
                           disparador=DISPARADOR_MANUAL)
    _tarea = asyncio.create_task(_ejecutar_tarea(fabrica, DISPARADOR_MANUAL))
    return True


async def ejecutar_automatico(fabrica) -> RescanReport | None:
    """Camino del bucle periódico: si hay una manual, o el cerrojo está tomado, salta y registra."""
    global _estado
    if _estado.en_curso:
        logger.info("rescan.auto_skipped", motivo="manual_en_curso")
        return None
    # Reserva el estado antes del await del cerrojo: un POST manual que llegue entre la
    # comprobación y la adquisición ve «en curso» y no crea otra tarea.
    _estado = EstadoRescan(fase=FaseRescan.CORRIENDO, iniciado=datetime.now(UTC),
                           disparador=DISPARADOR_AUTOMATICO)
    async with _cerrojo_ciclo(fabrica) as libre:
        if not libre:
            _estado = EstadoRescan()
            logger.info("rescan.auto_skipped", motivo="cerrojo_ocupado")
            return None
        tarea = tareas.iniciar("rescanear", enlace="/ui/auditoria#rescan-biblioteca",
                               origen="rescan")
        try:
            informe = await _correr(fabrica, DISPARADOR_AUTOMATICO)
            if tarea is not None:
                tareas.terminar(tarea.id, resumen="Biblioteca actualizada")
            _estado.informe = informe
            _estado.fase = FaseRescan.TERMINADO
            _estado.run_id = str(informe.run_id) if informe.run_id else None
            _estado.foco_resultado = True
            anotar_ultima(informe.started_at)
            return informe
        except asyncio.CancelledError:
            if tarea is not None:
                tareas.error(tarea.id, tipo_error="CancelledError")
            _estado.fase = FaseRescan.INACTIVO
            _estado.causa = "CancelledError"
            raise
        except Exception as exc:  # noqa: BLE001
            if tarea is not None:
                tareas.error(tarea.id, tipo_error=type(exc).__name__)
            _estado.fase = FaseRescan.ERROR
            _estado.causa = type(exc).__name__
            logger.warning("rescan.fallido", disparador=DISPARADOR_AUTOMATICO,
                           error=type(exc).__name__)
            return None
        finally:
            _estado.terminado = datetime.now(UTC)


async def detener() -> None:
    """Cancela la tarea manual en el apagado; no reanuda nada."""
    global _tarea, _estado
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _tarea
    _tarea = None
    _estado = EstadoRescan()


def reiniciar_para_pruebas() -> None:
    global _tarea, _estado, _ultima
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
    _tarea = None
    _estado = EstadoRescan()
    _ultima = None
