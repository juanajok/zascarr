# ruff: noqa: E501
"""Comprobar el disco a petición (#232, BL-R3a).

Una sola ejecución del ciclo del importador a la vez, manual o automática. El estado de la
ejecución vive en memoria (proceso único); el resultado y la última ejecución se leen de
`ImportRun`. El cerrojo es un advisory lock de sesión con clave propia `(326, 2)`: no se
reutiliza el de contenido `(326, 1)`, que es por transacción y por archivo.

El estado de #231 (`EstadoComprobacion`) es otra cosa: la observación persistida dentro del
ciclo. Este módulo usa `EstadoCicloDisco` y no lo mezcla.
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

from zascarr.services.ciclo_importador import ejecutar_ciclo_y_avisar
from zascarr.services.importer import Importer, ImportReport
from zascarr.services.notifier import Notifier

logger = structlog.get_logger()

#: Cerrojo de ciclo: namespace (326) ya usado por contenido, objeto 2 libre.
CLAVE_CERROJO_CICLO = (326, 2)

DISPARADOR_MANUAL = "manual"
DISPARADOR_AUTOMATICO = "automatico"


class FaseCicloDisco(StrEnum):
    INACTIVO = "inactivo"
    CORRIENDO = "corriendo"
    TERMINADO = "terminado"
    ERROR = "error"
    OCUPADO = "ocupado"


@dataclass
class EstadoCicloDisco:
    fase: FaseCicloDisco = FaseCicloDisco.INACTIVO
    iniciado: datetime | None = None
    terminado: datetime | None = None
    run_id: str | None = None
    disparador: str | None = None
    causa: str | None = None          # solo el TIPO de excepción; nunca mensaje ni ruta
    foco_resultado: bool = False      # el siguiente fragmento debe enfocar el resultado una vez

    @property
    def en_curso(self) -> bool:
        return self.fase is FaseCicloDisco.CORRIENDO


_estado = EstadoCicloDisco()
_tarea: asyncio.Task | None = None


def estado_actual() -> EstadoCicloDisco:
    return _estado


def consumir_foco_resultado() -> bool:
    """Devuelve True una sola vez, en el primer fragmento que ve el resultado."""
    if not _estado.foco_resultado:
        return False
    _estado.foco_resultado = False
    return True


@asynccontextmanager
async def _cerrojo_ciclo(fabrica):
    """Cerrojo de sesión en conexión propia; `try` sin espera.

    Si la fábrica no tiene bind (dobles de prueba), no hay cerrojo real: se comporta como libre.
    """
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


async def _correr(fabrica, disparador: str, ejecutar) -> ImportReport:
    return await ejecutar(Notifier(), fabrica, Importer, disparador=disparador)


async def _ejecutar_tarea(fabrica, disparador: str, ejecutar) -> None:
    async with _cerrojo_ciclo(fabrica) as libre:
        if not libre:
            _estado.fase = FaseCicloDisco.OCUPADO
            _estado.terminado = datetime.now(UTC)
            logger.info("comprobacion_disco.ocupado", disparador=disparador)
            return
        try:
            informe = await _correr(fabrica, disparador, ejecutar)
            _estado.fase = FaseCicloDisco.TERMINADO
            _estado.run_id = str(informe.run_id) if informe.run_id else None
            _estado.foco_resultado = True
            logger.info("comprobacion_disco.terminada", disparador=disparador,
                        run_id=_estado.run_id, importados=informe.imported_count)
        except asyncio.CancelledError:
            _estado.fase = FaseCicloDisco.INACTIVO
            _estado.causa = "CancelledError"
            raise
        except Exception as exc:  # noqa: BLE001 — el estado no propaga detalle técnico
            _estado.fase = FaseCicloDisco.ERROR
            _estado.causa = type(exc).__name__
            logger.warning("comprobacion_disco.fallida", disparador=disparador,
                           error=type(exc).__name__)
        finally:
            _estado.terminado = datetime.now(UTC)


def iniciar_manual(fabrica, *, ejecutar=None) -> bool:
    """Marca «en curso» y crea la tarea. Devuelve False si ya había una."""
    global _estado, _tarea
    if _estado.en_curso:
        return False
    _estado = EstadoCicloDisco(fase=FaseCicloDisco.CORRIENDO, iniciado=datetime.now(UTC),
                               disparador=DISPARADOR_MANUAL)
    _tarea = asyncio.create_task(
        _ejecutar_tarea(fabrica, DISPARADOR_MANUAL, ejecutar or ejecutar_ciclo_y_avisar))
    return True


async def ejecutar_automatico(fabrica, *, ejecutar=None) -> ImportReport | None:
    """Camino del bucle: si hay una manual, o el cerrojo está tomado, salta y registra."""
    global _estado
    if _estado.en_curso:
        logger.info("comprobacion_disco.auto_skipped", motivo="manual_en_curso")
        return None
    # Reserva el estado antes del await del cerrojo: un POST manual que llegue entre la
    # comprobación y la adquisición ve «en curso» y no crea otra tarea.
    _estado = EstadoCicloDisco(fase=FaseCicloDisco.CORRIENDO, iniciado=datetime.now(UTC),
                               disparador=DISPARADOR_AUTOMATICO)
    async with _cerrojo_ciclo(fabrica) as libre:
        if not libre:
            _estado = EstadoCicloDisco()
            logger.info("comprobacion_disco.auto_skipped", motivo="cerrojo_ocupado")
            return None
        try:
            informe = await _correr(fabrica, DISPARADOR_AUTOMATICO,
                                    ejecutar or ejecutar_ciclo_y_avisar)
            _estado.fase = FaseCicloDisco.TERMINADO
            _estado.run_id = str(informe.run_id) if informe.run_id else None
            _estado.foco_resultado = True
            return informe
        except asyncio.CancelledError:
            _estado.fase = FaseCicloDisco.INACTIVO
            _estado.causa = "CancelledError"
            raise
        except Exception as exc:  # noqa: BLE001
            _estado.fase = FaseCicloDisco.ERROR
            _estado.causa = type(exc).__name__
            logger.warning("comprobacion_disco.fallida", disparador=DISPARADOR_AUTOMATICO,
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
    _estado = EstadoCicloDisco()


def reiniciar_para_pruebas() -> None:
    global _tarea, _estado
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
    _tarea = None
    _estado = EstadoCicloDisco()
