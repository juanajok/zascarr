# ruff: noqa: E501
"""
Estado del sistema (E1) — semáforos en vez de JSON crudo.

Bug real (reportado): vivía como fichero estático fuera de base.html, sin
navegación de vuelta y con un look and feel distinto al resto de la app.
Ahora es una vista Jinja2 más, con el mismo topnav y las mismas clases de
web.css — el propio fetch() a /api/health en el navegador sigue siendo el
mismo (sin build tooling, sin JS nuevo del lado del servidor).

#231 (BL-R2): encima de los semáforos va el aviso de la última comprobación de la biblioteca, leído de la
base (lo que anotó el último ciclo), sin mirar el disco. Si la base no contesta, la página sigue sirviéndose
—es justo donde se mira cuando algo falla— y el aviso dice que no se ha podido leer.
"""
from __future__ import annotations

import contextlib

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services import disponibilidad
from zascarr.web.disponibilidad import registrar_filtros
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()
registrar_filtros(templates)

router = APIRouter(tags=["ui"])


@router.get("/estado", response_class=HTMLResponse)
async def estado(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    contexto: dict = {"disponibilidad_error": False, "d": None, "no_disponibles": 0}
    try:
        contexto["d"] = await disponibilidad.ultima_comprobacion(db)
        contexto["no_disponibles"] = await disponibilidad.contar_no_disponibles(db)
    except Exception as exc:  # noqa: BLE001 — la página de Estado no puede caerse por esto
        # Solo la clase del error: nunca rutas, consultas ni datos del coleccionista (CLAUDE.md §5.4).
        logger.warning("estado.disponibilidad_no_leida", error=type(exc).__name__)
        contexto["disponibilidad_error"] = True
        contexto["d"] = None
        # si la sesión ya no responde, se sirve la página igualmente
        with contextlib.suppress(Exception):
            await db.rollback()
    return templates.TemplateResponse(request, "estado.html", contexto)
