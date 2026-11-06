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
from datetime import UTC, datetime
from enum import StrEnum

import structlog
from sqlalchemy import text

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
    async with _cerrojo_ciclo(fabrica) as libre:
        if not libre:
            _estado.fase = FaseRescan.OCUPADO
            _estado.terminado = datetime.now(UTC)
            logger.info("rescan.ocupado", disparador=disparador)
            return
        try:
            informe = await _correr(fabrica, disparador)
            _estado.informe = informe
            _estado.fase = FaseRescan.TERMINADO
            _estado.run_id = str(informe.run_id) if informe.run_id else None
            _estado.foco_resultado = True
            logger.info(
                "rescan.terminado", disparador=disparador,
                run_id=_estado.run_id,
                revisados=informe.files_scanned,
                nuevos=informe.nuevos_registrados + informe.nuevos_a_revisar,
                re_triados=informe.re_triados,
                desaparecidos=informe.desaparecidos)
        except asyncio.CancelledError:
            _estado.fase = FaseRescan.INACTIVO
            _estado.causa = "CancelledError"
            raise
        except Exception as exc:  # noqa: BLE001 — el estado no propaga detalle técnico
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
        try:
            informe = await _correr(fabrica, DISPARADOR_AUTOMATICO)
            _estado.informe = informe
            _estado.fase = FaseRescan.TERMINADO
            _estado.run_id = str(informe.run_id) if informe.run_id else None
            _estado.foco_resultado = True
            return informe
        except asyncio.CancelledError:
            _estado.fase = FaseRescan.INACTIVO
            _estado.causa = "CancelledError"
            raise
        except Exception as exc:  # noqa: BLE001
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
    global _tarea, _estado
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
    _tarea = None
    _estado = EstadoRescan()
