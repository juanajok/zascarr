"""BL-C4 (#151): pantalla de arcos/sagas en orden de lectura."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.arcos import detalle_arco, listar_arcos
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/arcos", tags=["ui"])
templates = crear_templates()


def _respuesta(request: Request, plantilla: str, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("", response_class=HTMLResponse)
async def arcos(request: Request, pagina: int = Query(default=1, ge=1),
                db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    return _respuesta(request, "arcos.html", {
        "pagina": await listar_arcos(db, pagina)})


@router.get("/{arco_id}", response_class=HTMLResponse)
async def arco(arco_id: UUID, request: Request,
               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    detalle = await detalle_arco(db, arco_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Arco no encontrado")
    return _respuesta(request, "arco.html", {"arco": detalle})
