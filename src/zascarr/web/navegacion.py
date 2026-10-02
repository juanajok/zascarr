"""
Fragmento de contadores del menú (V3): `GET /ui/_nav/estado`.

Contrato (cada punto tiene su prueba):
  · Devuelve SOLO intercambios fuera de banda (`hx-swap-oob`) sobre los contadores del menú. La
    plantilla del menú pide con `hx-swap="none"`: este fragmento no puede reemplazar ni borrar un
    enlace, ni siquiera por error.
  · Ante CUALQUIER fallo —BD caída con la app ya en marcha (que en `/ui/*` es un 500 de texto
    plano), sesión caducada, arranque degradado— responde `204 No Content`: htmx no intercambia un
    204, y el menú queda como estaba. Nunca un 5xx con cuerpo.
  · Está bajo `/ui/*`, protegido por `AuthMiddleware` como el resto. NO se declara ruta de
    diagnóstico (eso la serviría sin comprobar la sesión). Sin sesión, el middleware responde 204
    vacío (ver `services/auth.py::RUTAS_FRAGMENTO_SILENCIOSO`): ni datos ni redirección a /login,
    que htmx seguiría y cuya página de acceso acabaría intercambiada.
"""
from __future__ import annotations

import contextlib

import structlog
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.navegacion import contadores
from zascarr.services.seguridad import estado_de_seguridad
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()

router = APIRouter(prefix="/ui/_nav", tags=["ui"], include_in_schema=False)

SIN_CONTENIDO = 204
#: sin caché: un contador viejo en una caché intermedia sería peor que no tenerlo
CABECERAS = {"Cache-Control": "no-store"}


@router.get("/estado", response_class=HTMLResponse)
async def contadores_del_menu(request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    try:
        cuentas = await contadores(db)
        atencion = bool(estado_de_seguridad()["atencion"])
    except Exception as exc:  # noqa: BLE001 — cualquier fallo se degrada a «no cambies nada»
        # Solo la clase del error: nunca rutas, consultas ni datos del coleccionista (§5.4).
        logger.warning("nav_contadores_no_disponibles", error=type(exc).__name__)
        # La sesión puede haber quedado inservible: se deshace para no ensuciar el cierre de get_db.
        with contextlib.suppress(Exception):
            await db.rollback()
        return Response(status_code=SIN_CONTENIDO, headers=CABECERAS)
    return templates.TemplateResponse(
        request, "_nav_contadores.html",
        {"pendientes": cuentas.pendientes, "deseados": cuentas.deseados, "atencion": atencion},
        headers=CABECERAS,
    )
