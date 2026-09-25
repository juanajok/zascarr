"""
Router de descubrimiento de series (C0) — /ui/descubrir.

Busca en fuentes externas (Comic Vine/AniList/Tebeosfera, vía
DiscoveryService) y da de alta la `Series` local que Wishlist y el
matcher necesitan para funcionar — ver el docstring de
services/discovery.py para el porqué. Dar de alta una serie es
catalogar metadatos, no descargar nada: a diferencia de
`/ui/wishlist/anadir`, esta ruta NO lleva `require_legal_acknowledgment`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import DiscoveryService
from zascarr.web.library import _TRADICION_LABEL
from zascarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/descubrir", tags=["ui"])


@router.get("", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "descubrir.html", {})


@router.get("/buscar", response_class=HTMLResponse)
async def buscar(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    resultados, avisos = await DiscoveryService(db).search(q)
    tradiciones = [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition]
    return templates.TemplateResponse(
        request, "_resultados_descubrir.html",
        {"resultados": resultados, "avisos": avisos, "tradiciones": tradiciones},
    )


@router.post("/crear", response_class=HTMLResponse)
async def crear(
    request: Request,
    source: MetadataSource = Form(...),
    external_id: str = Form(...),
    title: str = Form(...),
    tradition: ComicTradition = Form(...),
    start_year: int | None = Form(default=None),
    description: str | None = Form(default=None),
    cover_url: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    try:
        series, creada = await DiscoveryService(db).get_or_create_series(
            source=source, external_id=external_id, title=title,
            tradition=tradition, start_year=start_year,
            description=description, cover_url=cover_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request, "_serie_creada.html", {"series": series, "creada": creada}
    )
