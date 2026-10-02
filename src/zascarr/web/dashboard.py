"""
Inicio de biblioteca — vista principal de ZascArr (GET /ui/).

Router fino: el estado sale de `services/inicio.py` (V4), no se calcula aquí ni en la plantilla.
No añade tablas ni funcionalidad de dominio.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.inicio import cargar_inicio
from zascarr.services.primeros_pasos import fecha_llana
from zascarr.web.routes import crear_templates

templates = crear_templates()
templates.env.filters["fecha_llana"] = fecha_llana

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Inicio: primeros pasos derivados del estado y las cifras de la colección."""
    vista = await cargar_inicio(db)
    return templates.TemplateResponse(request, "dashboard.html", {"v": vista})
