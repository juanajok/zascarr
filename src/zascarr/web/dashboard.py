"""
Inicio de biblioteca — vista principal de ZascArr (GET /ui/).

Router fino: las cifras salen de `services/resumen.py` (V4), no se calculan aquí ni en la
plantilla. No añade tablas ni funcionalidad de dominio.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.resumen import resumen_biblioteca
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Inicio con las métricas de la colección."""
    resumen = await resumen_biblioteca(db)
    return templates.TemplateResponse(request, "dashboard.html", {
        "total_series": resumen.total_series,
        "series_con_archivos": resumen.series_con_archivos,
        "porcentaje_completitud": resumen.porcentaje_completitud,
        "total_issues": resumen.total_issues,
        "huecos_pendientes": resumen.huecos_pendientes,
        "ultimas_series": resumen.ultimas_series,
    })
