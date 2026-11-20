"""
Aviso legal — /ui/legal (wizard de aceptación) y /legal (texto completo,
solo lectura). Ninguna de las dos rutas lleva
Depends(require_legal_acknowledgment): tienen que ser alcanzables
precisamente para poder aceptar el aviso o simplemente leerlo.
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.legal import (
    RETORNO_LEGAL_POR_DEFECTO,
    acknowledge,
    current_legal_version,
    get_acknowledgment,
    render_legal_html,
    resolver_destino_legal,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(tags=["ui"])


@router.get("/ui/legal", response_class=HTMLResponse)
async def wizard(request: Request, volver: str = Query(default=""),
                 falta: str = Query(default=""),
                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    ack = await get_acknowledgment(db)
    destino = resolver_destino_legal(request, volver)
    respuesta = templates.TemplateResponse(request, "legal_wizard.html", {
        "accepted": ack is not None,
        "accepted_at": ack.accepted_at if ack else None,
        "legal_version": current_legal_version(),
        "volver": destino or RETORNO_LEGAL_POR_DEFECTO,
        "falta": falta == "1",
        # Solo se promete conservar el destino si de verdad se conservó: si
        # ningún candidato valía, ya se cayó al respaldo antes de pintar el aviso.
        "destino_conservado": destino is not None,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/ui/legal/accept")
async def accept(
    request: Request,
    acepto_1: bool = Form(default=False), acepto_2: bool = Form(default=False),
    acepto_3: bool = Form(default=False), volver: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    destino = resolver_destino_legal(request, volver)
    if not (acepto_1 and acepto_2 and acepto_3):
        falta = "/ui/legal?falta=1"
        if destino is not None:
            falta = f"/ui/legal?volver={quote(destino, safe='')}&falta=1"
        return RedirectResponse(falta, status_code=303,
                                headers={"Cache-Control": "no-store"})
    await acknowledge(db)
    return RedirectResponse(destino or RETORNO_LEGAL_POR_DEFECTO, status_code=303,
                            headers={"Cache-Control": "no-store"})


@router.get("/legal", response_class=HTMLResponse)
async def full_text(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "legal_full.html", {"legal_html": render_legal_html()}
    )
