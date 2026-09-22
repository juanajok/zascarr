"""
Biblioteca (C1) — /ui/biblioteca. Primera pantalla de navegación real:
hasta ahora solo existían pantallas de un único propósito (pendientes,
wishlist) y una ficha de serie (C2) alcanzable solo por URL directa.

Filtros por tradición/editorial vía dropdown (universos cerrados y
pequeños); por personaje/saga vía búsqueda-y-navegación (el universo
puede ser grande, no cabe en un dropdown) — clicar un resultado navega a
`/ui/biblioteca?character_id=...`, un reset simple de los demás filtros
que se acepta a propósito para no complicar la UI con JS de por medio
(ADR-0001: sin más JS que HTMX declarativo por ahora).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.database import get_db
from secuenciarr.models import ComicTradition
from secuenciarr.services.series import SeriesService
from secuenciarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/biblioteca", tags=["ui"])

_TRADICION_LABEL = {
    ComicTradition.AMERICAN: "Grapa americana",
    ComicTradition.FRANCO_BELGIAN: "Franco-belga (BD)",
    ComicTradition.MANGA: "Manga",
    ComicTradition.TEBEO: "Tebeo español",
    ComicTradition.FUMETTI: "Fumetti",
    ComicTradition.MANHWA: "Manhwa",
    ComicTradition.MANHUA: "Manhua",
    ComicTradition.BRITISH: "Británico",
    ComicTradition.OTHER: "Otra",
}


def _uuid_or_none(value: str) -> UUID | None:
    """Los campos ocultos del filtro llegan como "" cuando no hay
    personaje/saga/editorial seleccionados — FastAPI no acepta "" para
    un parámetro tipado UUID | None (intenta parsearlo y da 422),
    así que estos tres llegan como str y se convierten aquí a mano."""
    value = (value or "").strip()
    return UUID(value) if value else None


async def _resultados_context(
    db: AsyncSession, page: int, tradition: str, publisher_id: str,
    character_id: str, story_arc_id: str, q: str,
) -> dict:
    publisher_uuid = _uuid_or_none(publisher_id)
    character_uuid = _uuid_or_none(character_id)
    story_arc_uuid = _uuid_or_none(story_arc_id)
    items, total = await SeriesService(db).list_series(
        page=page, page_size=24, tradition=tradition or None, search=q or None,
        publisher_id=publisher_uuid, character_id=character_uuid, story_arc_id=story_arc_uuid,
    )
    pages = (total + 24 - 1) // 24
    return {
        "items": items, "page": page, "pages": pages, "total": total,
        "tradition": tradition or "", "publisher_id": publisher_uuid, "q": q or "",
        "character_id": character_uuid, "story_arc_id": story_arc_uuid,
    }


@router.get("", response_class=HTMLResponse)
async def index(
    request: Request, page: int = 1, tradition: str = "", publisher_id: str = "",
    character_id: str = "", story_arc_id: str = "", q: str = "",
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    service = SeriesService(db)
    publishers = await service.list_publishers_with_series()
    ctx = await _resultados_context(db, page, tradition, publisher_id, character_id, story_arc_id, q)
    ctx.update({
        "publishers": publishers,
        "tradiciones": [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition],
    })
    return templates.TemplateResponse(request, "biblioteca.html", ctx)


@router.get("/resultados", response_class=HTMLResponse)
async def resultados(
    request: Request, page: int = 1, tradition: str = "", publisher_id: str = "",
    character_id: str = "", story_arc_id: str = "", q: str = "",
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    ctx = await _resultados_context(db, page, tradition, publisher_id, character_id, story_arc_id, q)
    return templates.TemplateResponse(request, "_rejilla_biblioteca.html", ctx)


@router.get("/buscar-personaje", response_class=HTMLResponse)
async def buscar_personaje(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    characters = await SeriesService(db).search_characters(q)
    return templates.TemplateResponse(request, "_resultados_personaje.html", {"characters": characters})


@router.get("/buscar-saga", response_class=HTMLResponse)
async def buscar_saga(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    story_arcs = await SeriesService(db).search_story_arcs(q)
    return templates.TemplateResponse(request, "_resultados_saga.html", {"story_arcs": story_arcs})
