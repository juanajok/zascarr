"""
Router de la bandeja de pendientes (B2) — /ui/pendientes.

Archivos que el importer no supo clasificar (viven en _Unsorted/, ver
ReviewService). Cada acción es un endpoint HTMX que devuelve el
fragmento HTML que reemplaza la tarjeta o los resultados de búsqueda;
la lógica de negocio vive en ReviewService, no aquí.
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.database import get_db
from secuenciarr.models import File
from secuenciarr.services.review import ReviewService
from secuenciarr.utils.cover import extract_cover_thumbnail
from secuenciarr.utils.naming import parse_comic_filename
from secuenciarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/pendientes", tags=["ui"])


def _detected_label(filename: str) -> str:
    parsed = parse_comic_filename(filename)
    if not parsed.series:
        return "Sin detectar"
    return f"{parsed.series} #{parsed.issue_number}" if parsed.issue_number else parsed.series


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    files = await ReviewService(db).pending_files()
    cards = [{"file": f, "detected": _detected_label(f.file_name)} for f in files]
    return templates.TemplateResponse(request, "pendientes.html", {"cards": cards})


@router.get("/{file_id}/portada")
async def portada(file_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    file = await db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    result = extract_cover_thumbnail(Path(file.file_path))
    if result is None:
        raise HTTPException(status_code=404, detail="Sin miniatura disponible")
    data, content_type = result
    return Response(content=data, media_type=content_type)


@router.get("/{file_id}/buscar-serie", response_class=HTMLResponse)
async def buscar_serie(file_id: UUID, request: Request, q: str = "",
                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series_list = await ReviewService(db).search_series(q)
    return templates.TemplateResponse(
        request, "_resultados_serie.html", {"file_id": file_id, "series_list": series_list}
    )


@router.post("/{file_id}/asignar", response_class=HTMLResponse)
async def asignar(file_id: UUID, series_id: UUID = Form(...), issue_number: str = Form(...),
                   db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await ReviewService(db).assign_to_series(file_id, series_id, issue_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return HTMLResponse("")  # la tarjeta se reemplaza por nada: desaparece de la bandeja


@router.post("/{file_id}/ignorar", response_class=HTMLResponse)
async def ignorar(file_id: UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await ReviewService(db).dismiss(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse("")
