"""
Router de la lista de deseos (D1) — /ui/wishlist.

Buscar una serie ya existente en la biblioteca y marcarla como deseada;
el ciclo de fondo (`_orchestrator_loop`, ver main.py) se encarga de
buscarla, descargarla e importarla solo. Esta pantalla solo refleja el
estado (`Wishlist.status`) — la lógica de negocio vive en WishlistService,
no aquí, mismo patrón que pendientes.py/ReviewService (B2).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.database import get_db
from zascarr.models import Issue, Wishlist, WishlistStatus
from zascarr.services.legal import require_legal_acknowledgment
from zascarr.services.wishlist import WishlistService
from zascarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/wishlist", tags=["ui"])

_ESTADO_LABEL = {
    WishlistStatus.WANTED: "Buscando…",
    WishlistStatus.SEARCHING: "Buscando…",
    WishlistStatus.DOWNLOADING: "Descargando…",
    WishlistStatus.DOWNLOADED: "Descargando…",
    WishlistStatus.IMPORTED: "En tu biblioteca",
    WishlistStatus.FAILED: "Sin resultados",
}

# Carga anticipada de las relaciones que _row() necesita, para no disparar
# lazy-load asíncrono (MissingGreenlet) al leer item.series/item.issue.series
# fuera de una llamada await explícita — mismo cuidado que enricher.py
# documenta para issue.credits.
_EAGER = (selectinload(Wishlist.series), selectinload(Wishlist.issue).selectinload(Issue.series))


def _row(item: Wishlist) -> dict:
    series = item.series or (item.issue.series if item.issue else None)
    titulo = series.title if series else "?"
    if item.issue and item.issue.issue_number:
        titulo = f"{titulo} #{item.issue.issue_number}"
    return {
        "item": item,
        "titulo": titulo,
        "estado": _ESTADO_LABEL.get(item.status, item.status.value),
        "puede_reintentar": item.status == WishlistStatus.FAILED,
    }


async def _get_row(db: AsyncSession, item_id) -> dict:
    item = (await db.execute(
        select(Wishlist).options(*_EAGER).where(Wishlist.id == item_id)
    )).scalar_one()
    return _row(item)


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    items = list((await db.execute(
        select(Wishlist).options(*_EAGER).order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
    )).scalars().all())
    rows = [_row(item) for item in items]
    return templates.TemplateResponse(request, "wishlist.html", {"rows": rows})


@router.get("/buscar-serie", response_class=HTMLResponse)
async def buscar_serie(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series_list = await WishlistService(db).search_series(q)
    return templates.TemplateResponse(
        request, "_resultados_series_wishlist.html", {"series_list": series_list}
    )


@router.post("/anadir", response_class=HTMLResponse, dependencies=[Depends(require_legal_acknowledgment)])
async def anadir(request: Request, series_id: UUID = Form(...), db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        item = await WishlistService(db).add(series_id=series_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await _get_row(db, item.id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})


@router.post("/{item_id}/quitar", response_class=HTMLResponse)
async def quitar(item_id: UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await WishlistService(db).remove(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse("")


@router.post("/{item_id}/reintentar", response_class=HTMLResponse, dependencies=[Depends(require_legal_acknowledgment)])
async def reintentar(item_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await WishlistService(db).retry(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    row = await _get_row(db, item_id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})
