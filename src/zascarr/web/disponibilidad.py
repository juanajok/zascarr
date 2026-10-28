# ruff: noqa: E501
"""Archivos no disponibles (BL-R2, #231) — `/ui/no-disponibles`.

Lista de SOLO LECTURA de los archivos que el ciclo del importador marcó como no encontrados, más lo que comprobó
la última vez (ver `services/disponibilidad.py`). Abrirla o paginarla no toca el disco, no lanza ninguna comprobación
y no modifica nada: lo observado se lee de la base. Lanzar una comprobación a mano pertenece a #232.

Si no puede leerse, dice que no ha podido: nunca una lista vacía que parezca «todo disponible».
"""
from __future__ import annotations

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services import disponibilidad
from zascarr.services.primeros_pasos import fecha_llana, hace_cuanto
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()


def _fecha_con_antiguedad(fecha: datetime) -> str:
    """«3 de octubre de 2026 (hace 5 días)»: la fecha exacta y si es reciente, sin hacer cuentas."""
    return f"{fecha_llana(fecha)} ({hace_cuanto(fecha, datetime.now(UTC))})"


def registrar_filtros(plantillas) -> None:
    """Para las pantallas que enseñan el aviso de la última comprobación (esta y Estado)."""
    plantillas.env.filters["fecha_con_antiguedad"] = _fecha_con_antiguedad


registrar_filtros(templates)

router = APIRouter(prefix="/ui/no-disponibles", tags=["ui"])


@router.get("", response_class=HTMLResponse)
async def no_disponibles(request: Request, despues: str | None = None,
                         db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        comprobacion = await disponibilidad.ultima_comprobacion(db)
        pagina = await disponibilidad.listar_no_disponibles(db, despues)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de lectura se dice, no se disfraza de lista vacía
        # Solo la clase del error: nunca rutas, consultas ni datos del coleccionista (CLAUDE.md §5.4).
        logger.warning("no_disponibles.lectura_fallida", error=type(exc).__name__)
        await db.rollback()
        return templates.TemplateResponse(request, "no_disponibles.html", {"error": True}, status_code=503)
    return templates.TemplateResponse(request, "no_disponibles.html", {
        "error": False, "d": comprobacion, "pagina": pagina, "primera": despues is None
    })
