"""
Aviso legal — /ui/legal (wizard de aceptación) y /legal (texto completo,
solo lectura). Ninguna de las dos rutas lleva
Depends(require_legal_acknowledgment): tienen que ser alcanzables
precisamente para poder aceptar el aviso o simplemente leerlo.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.database import get_db
from secuenciarr.services.legal import (
    acknowledge, current_legal_version, get_acknowledgment, render_legal_html,
)
from secuenciarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(tags=["ui"])


@router.get("/ui/legal", response_class=HTMLResponse)
async def wizard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    ack = await get_acknowledgment(db)
    return templates.TemplateResponse(request, "legal_wizard.html", {
        "accepted": ack is not None,
        "accepted_at": ack.accepted_at if ack else None,
        "legal_version": current_legal_version(),
    })


@router.post("/ui/legal/accept")
async def accept(
    acepto_1: bool = Form(default=False), acepto_2: bool = Form(default=False),
    acepto_3: bool = Form(default=False), db: AsyncSession = Depends(get_db),
):
    if not (acepto_1 and acepto_2 and acepto_3):
        return RedirectResponse("/ui/legal", status_code=303)
    await acknowledge(db)
    return RedirectResponse("/ui/biblioteca", status_code=303)


@router.get("/legal", response_class=HTMLResponse)
async def full_text(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal_full.html", {"legal_html": render_legal_html()})
