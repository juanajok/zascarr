"""
Router de la bandeja de pendientes (B2) — /ui/pendientes.

Archivos que el importer no supo clasificar (viven en _Unsorted/, ver
ReviewService). Cada acción es un endpoint HTMX que devuelve el
fragmento HTML que reemplaza la tarjeta o los resultados de búsqueda;
la lógica de negocio vive en ReviewService, no aquí.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import File
from zascarr.services.review import ReviewService
from zascarr.utils.cover import cached_image_response, extract_cover_thumbnail
from zascarr.utils.naming import parse_comic_filename
from zascarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/pendientes", tags=["ui"])


def _detected_label(filename: str) -> str:
    parsed = parse_comic_filename(filename)
    if not parsed.series:
        return "Sin detectar"
    return f"{parsed.series} #{parsed.issue_number}" if parsed.issue_number else parsed.series


def _suggestion(file: File) -> dict | None:
    """B12: mejor candidato guardado por el matcher (naming.py SÍ extrajo
    título+número pero no hubo serie que igualara con confianza) — se
    ofrece como sugerencia de un clic, nunca como autoasignación. El
    número de issue se prefilla del propio nombre de archivo cuando el
    parser lo detectó; si no, el coleccionista lo escribe a mano igual
    que en una búsqueda manual."""
    candidatos = (file.metadata_ or {}).get("candidates") or []
    if not candidatos:
        return None
    mejor = candidatos[0]
    parsed = parse_comic_filename(file.file_name)
    return {
        "series_id": mejor["series_id"],
        "title": mejor["title"],
        "start_year": mejor.get("start_year"),
        "score_pct": round(mejor["score"] * 100),
        "issue_number": parsed.issue_number or "",
    }


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    files = await ReviewService(db).pending_files()
    cards = [
        {"file": f, "detected": _detected_label(f.file_name), "suggestion": _suggestion(f)}
        for f in files
    ]
    return templates.TemplateResponse(request, "pendientes.html", {"cards": cards})


@router.get("/{file_id}/portada")
async def portada(file_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    file = await db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = Path(file.file_path)
    # extract_cover_thumbnail es zipfile+Pillow, síncrono y bloqueante:
    # se manda a un hilo aparte para no congelar el event loop (M4).
    result = await asyncio.to_thread(extract_cover_thumbnail, path)
    if result is None:
        raise HTTPException(status_code=404, detail="Sin miniatura disponible")
    data, content_type = result
    etag = f'"{path.stat().st_mtime}"'
    return cached_image_response(request, data, content_type, etag)


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
