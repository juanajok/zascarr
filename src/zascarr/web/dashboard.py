"""
Inicio de biblioteca — vista principal de ZascArr (GET /ui/).

Router fino: el estado sale de `services/inicio.py` (V4), no se calcula aquí ni en la plantilla.
No añade tablas ni funcionalidad de dominio.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.inicio import cargar_inicio
from zascarr.services.primeros_pasos import fecha_llana
from zascarr.utils.registro_reciente import texto_reciente
from zascarr.web.routes import crear_templates

templates = crear_templates()
templates.env.filters["fecha_llana"] = fecha_llana

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Inicio: primeros pasos derivados del estado y las cifras de la colección."""
    vista = await cargar_inicio(db)
    return templates.TemplateResponse(request, "dashboard.html", {"v": vista})


@router.get("/logs")
async def descargar_logs() -> Response:
    """BL-E5 (#164): últimos eventos de la app como fichero, sin shell ni Docker."""
    ahora = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=texto_reciente(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="zascarr-logs-{ahora}.txt"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
