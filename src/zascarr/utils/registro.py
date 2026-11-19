"""Configuración única de logging de ZascArr.

El formato y el nivel se deciden aquí, no en cada módulo: JSON estructurado en
producción (Docker recoge stdout), consola legible si `LOG_JSON=false`, y
`LOG_LEVEL` aplicado de verdad. Los campos son estables para poder filtrar por
`event`, `level`, `request_id` o `timestamp` sin parsear texto libre.

No sustituye al saneador de `SEC-LOG` (#369): la cadena de structlog sigue
pasando por `sanear_evento` antes del render final.
"""
from __future__ import annotations

import logging
import sys

import structlog

_RENDER_EXCEPCION = structlog.processors.ExceptionRenderer()


def _formatear_exc_info(_logger, _metodo, evento):
    """Nombre estable para que el saneador y las pruebas lo reconozcan."""
    return _RENDER_EXCEPCION(_logger, _metodo, evento)


_NIVELES = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "warn": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}


def nivel_de_log(valor: str | None) -> tuple[int, str]:
    """Nivel efectivo y nombre canónico; un valor raro cae a INFO."""
    nombre = str(valor or "INFO").strip().lower()
    if nombre not in _NIVELES:
        return logging.INFO, "info"
    return _NIVELES[nombre], ("warning" if nombre == "warn" else nombre)


def configurar_logs(settings=None) -> None:
    """Instala structlog con formato y nivel reales (idempotente en la práctica)."""
    from zascarr.config import get_settings

    ajustes = settings or get_settings()
    nivel, nombre_nivel = nivel_de_log(getattr(ajustes, "log_level", "INFO"))
    # En Docker stdout no es una terminal: los colores solo ensucian el fichero.
    consola = bool(getattr(ajustes, "log_json", True)) is False
    renderer = (
        structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
        if consola
        else structlog.processors.JSONRenderer(ensure_ascii=False, sort_keys=True)
    )
    # Conserva el saneador (#369) y el capturador de /ui/logs si ya estaban
    # instalados: reconfigurar el formato no debe desactivar la privacidad.
    previos = list(structlog.get_config().get("processors") or [])
    conservar = [p for p in previos
                 if getattr(p, "__name__", "") in {"sanear_evento", "escribir_evento", "capturar"}]
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
            structlog.processors.StackInfoRenderer(),
            _formatear_exc_info,
            *conservar,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(nivel),
        logger_factory=structlog.PrintLoggerFactory(),
        # False a propósito: `capture_logs` de las pruebas y una
        # reconfiguración en caliente deben ver los procesadores nuevos.
        cache_logger_on_first_use=False,
    )
    # stdlib/uvicorn: mismo umbral, sin añadir un segundo handler (uvicorn ya
    # escribe su acceso) y sin bajar httpx/httpcore, que podrían filtrar URLs.
    logging.getLogger().setLevel(nivel)
    for nombre in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(nombre).setLevel(nivel)
    for nombre in ("httpx", "httpcore"):
        logging.getLogger(nombre).setLevel(logging.WARNING)
    structlog.get_logger().debug("zascarr.logging_config", level=nombre_nivel,
                                 formato="console" if consola else "json")
