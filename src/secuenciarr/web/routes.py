"""
Router de la UI web (/ui/*) — ver docs/adr/0001-ui-stack.md.

Separado del router /api a propósito: las plantillas llaman a la misma
capa de servicios que ya usa la API (Importer, EnrichmentService...), no
una segunda copia de la lógica de negocio. Esto es solo el esqueleto:
una página placeholder que prueba que Jinja2 + HTMX cargan correctamente.
La primera pantalla real (B2, bandeja de pendientes) se construye sobre
este mismo layout en el siguiente paso.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html", {})
