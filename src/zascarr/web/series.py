"""
Ficha de serie (C2, ampliada en C1) — /ui/series/{id}.

C2 dejó solo números presentes/ausentes. C1 añade portada (cascada
unificada de 3 niveles, ver docstring de portada() abajo), editorial y
géneros, y un enlace de vuelta a /ui/biblioteca — sigue sin ser el
diseño final de una ficha de serie, solo deja de estar pelada.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.api.series import _fetch_sort_orders, compute_missing_issues
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import File, Issue, Series
from zascarr.utils.cover import cached_image_response, extract_cover_thumbnail, fetch_and_cache_cover, write_cover_cache
from zascarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/series", tags=["ui"])


@router.get("/{series_id}", response_class=HTMLResponse)
async def detalle(series_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = (await db.execute(
        select(Series)
        .options(selectinload(Series.publisher), selectinload(Series.genres))
        .where(Series.id == series_id)
    )).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    sort_orders = await _fetch_sort_orders(db, series_id)
    present = sorted(int(n) if n.is_integer() else n for n in sort_orders)
    missing = compute_missing_issues(series.total_issues, sort_orders)

    return templates.TemplateResponse(request, "series_detail.html", {
        "series": series, "present": present, "missing": missing,
    })


@router.get("/{series_id}/portada")
async def portada(series_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    """Cascada unificada de 3 niveles (C1):

    1. ¿Ya está cacheada en disco (venga de donde venga)? Servirla.
    2. Si no, ¿hay algún archivo ya importado de esta serie? Extraer su
       primera página, cachearla, servirla.
    3. Si no, ¿tiene `cover_url` de una fuente externa? Descargarla una
       vez, cachearla, servirla.
    4. Si nada de eso, 404 — el <img> del template cae al placeholder
       CSS (.cover-missing), igual que en pendientes.html.

    Nunca se cachea una AUSENCIA: si no hay portada todavía, la próxima
    petición vuelve a intentarlo (barato: un exists() + una query).
    Todo el trabajo bloqueante (zipfile, Pillow, disco) va a un hilo
    aparte para no congelar el event loop.
    """
    series = await db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    cache_path = get_settings().covers_cache_path / f"{series_id}.jpg"

    if await asyncio.to_thread(cache_path.exists):
        data = await asyncio.to_thread(cache_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(cache_path))

    row = (await db.execute(
        select(File.file_path)
        .join(Issue, File.issue_id == Issue.id)
        .where(Issue.series_id == series_id)
        .order_by(Issue.sort_order.asc().nulls_last())
        .limit(1)
    )).first()
    if row:
        result = await asyncio.to_thread(extract_cover_thumbnail, Path(row[0]))
        if result:
            data, content_type = result
            await asyncio.to_thread(write_cover_cache, cache_path, data)
            return cached_image_response(request, data, content_type, _etag_for(cache_path))

    if series.cover_url and await fetch_and_cache_cover(series.cover_url, cache_path):
        data = await asyncio.to_thread(cache_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(cache_path))

    raise HTTPException(status_code=404, detail="Sin portada disponible")


def _etag_for(path: Path) -> str:
    return f'"{path.stat().st_mtime}"'
