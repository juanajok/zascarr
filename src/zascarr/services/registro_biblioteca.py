# ruff: noqa: E501
"""Registro de la biblioteca en SEGUNDO PLANO, con progreso consultable.

Registrar una biblioteca grande lee (para el sha256) cada archivo: en una Pi con el disco por USB son
minutos. Hacerlo dentro de una petición HTTP significaría una página colgada, un cierre de pestaña que
cancela el trabajo y, con una sola transacción, perder TODO lo hecho. Aquí el trabajo corre en su propia
tarea con su propia sesión, confirma por lotes (`LibraryAdopter.adopt`) y la interfaz solo consulta.

Contrato:
  · Una sola ejecución a la vez por proceso (la imagen corre con `--workers 1`). Dos peticiones seguidas no
    lanzan dos registros; la segunda ve el progreso de la primera.
  · NO se reanuda sola al reiniciar (no hay escrituras inesperadas al arrancar): quien quiera continuar lo
    pide, y como el registro es idempotente por ruta, continúa donde se quedó.
  · Un fallo general (BD caída, etc.) deja el estado en «interrumpido» con una causa SANEADA (el tipo de error,
    nunca rutas ni mensajes) y lo ya confirmado se conserva.
  · «Terminado» no significa «correcto»: la interfaz tiene que mirar `errores` antes de anunciar éxito.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

import structlog

from zascarr.services.library_adopter import AdoptionReport, LibraryAdopter

logger = structlog.get_logger()


class FaseRegistro(StrEnum):
    INACTIVO = "inactivo"
    CORRIENDO = "corriendo"
    TERMINADO = "terminado"          # el recorrido acabó (puede haber errores por archivo)
    INTERRUMPIDO = "interrumpido"    # cayó antes de acabar: lo ya confirmado se conserva


@dataclass
class EstadoRegistro:
    fase: FaseRegistro = FaseRegistro.INACTIVO
    iniciado: datetime | None = None
    terminado: datetime | None = None
    ya_registrados: int = 0
    total: int = 0
    procesados: int = 0
    registrados: int = 0
    sin_identificar: int = 0
    repetidos: int = 0
    otra_ejecucion: int = 0
    #: mirados pero aún SIN confirmar en la BD (el lote en curso)
    en_lote: int = 0
    #: mirados de un lote que NO se guardó (el commit falló y se comprobó que no quedó nada)
    no_guardados: int = 0
    #: mirados de un lote cuyo commit falló y no se pudo comprobar si se guardó
    por_comprobar: int = 0
    errores: list[str] = field(default_factory=list)
    causa: str | None = None          # solo si INTERRUMPIDO: el TIPO de error, nunca el mensaje

    @property
    def completo(self) -> bool:
        """Terminó, sin errores y sin interrupción: el único caso en el que se puede decir «registrada»."""
        return self.fase is FaseRegistro.TERMINADO and not self.errores

    @property
    def anadidos(self) -> int:
        """Lo que REALMENTE entró en el catálogo: no es lo mismo que lo procesado (hubo repetidos, errores…)."""
        return self.registrados + self.sin_identificar

    @property
    def en_marcha(self) -> bool:
        return self.fase is FaseRegistro.CORRIENDO


_estado = EstadoRegistro()
_tarea: asyncio.Task | None = None


def estado_actual() -> EstadoRegistro:
    return _estado


def _volcar(report: AdoptionReport) -> None:
    _estado.ya_registrados = report.already_registered
    _estado.total = report.to_process
    _estado.procesados = report.processed
    _estado.registrados = report.registered_count
    _estado.sin_identificar = report.unsorted_count
    _estado.repetidos = report.duplicate_count
    _estado.otra_ejecucion = report.by_other_run
    _estado.en_lote = report.pending_count
    _estado.no_guardados = report.reverted
    _estado.por_comprobar = report.unknown
    _estado.errores = list(report.errors)


async def _ejecutar(fabrica: Callable) -> None:
    try:
        async with fabrica() as sesion:
            informe = await LibraryAdopter(sesion).adopt(progreso=_volcar)
        _volcar(informe)
        _estado.fase = FaseRegistro.TERMINADO
    except asyncio.CancelledError:
        _estado.fase = FaseRegistro.INTERRUMPIDO
        _estado.causa = "CancelledError"
        raise
    except Exception as exc:  # noqa: BLE001 — nada se propaga: se cuenta en el estado
        logger.warning("registro_biblioteca.interrumpido", error=type(exc).__name__)
        _estado.fase = FaseRegistro.INTERRUMPIDO
        _estado.causa = type(exc).__name__
    finally:
        _estado.terminado = datetime.now(UTC)


def iniciar(fabrica: Callable) -> bool:
    """Lanza el registro. Devuelve False si ya hay uno en marcha (y no hace nada)."""
    global _estado, _tarea
    if _estado.en_marcha and _tarea is not None and not _tarea.done():
        return False
    _estado = EstadoRegistro(fase=FaseRegistro.CORRIENDO, iniciado=datetime.now(UTC))
    _tarea = asyncio.create_task(_ejecutar(fabrica))
    return True


def reiniciar_para_pruebas() -> None:
    """Solo para tests: deja el módulo como recién importado (cancelando lo que hubiera)."""
    global _estado, _tarea
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
    _estado, _tarea = EstadoRegistro(), None
