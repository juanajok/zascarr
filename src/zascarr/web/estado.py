"""
Estado del sistema (E1) — semáforos en vez de JSON crudo.

Bug real (reportado): vivía como fichero estático fuera de base.html, sin
navegación de vuelta y con un look and feel distinto al resto de la app.
Ahora es una vista Jinja2 más, con el mismo topnav y las mismas clases de
web.css — el propio fetch() a /api/health en el navegador sigue siendo el
mismo (sin build tooling, sin JS nuevo del lado del servidor).
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(tags=["ui"])


@router.get("/estado", response_class=HTMLResponse)
async def estado(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "estado.html", {})
