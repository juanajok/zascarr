"""
Ficha de serie mínima (C2) — /ui/series/{id}.

Solo lo que pide C2: números presentes/ausentes de una serie, usando el
cálculo ya corregido (compute_missing_issues, api/series.py). El resto de
la ficha real — pósters, filtros por tradición/editorial/personaje,
navegación desde una biblioteca — es trabajo de C1, que todavía no
existe; esta pantalla se ampliará o se rehará entonces, no es el diseño
final. Alcanzable solo por URL directa por ahora, sin enlace en el
topnav: no hay desde dónde navegar a ella sin C1.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.api.series import _fetch_sort_orders, compute_missing_issues
from secuenciarr.database import get_db
from secuenciarr.models import Series
from secuenciarr.web.routes import TEMPLATES_DIR

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter(prefix="/ui/series", tags=["ui"])


@router.get("/{series_id}", response_class=HTMLResponse)
async def detalle(series_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    sort_orders = await _fetch_sort_orders(db, series_id)
    present = sorted(int(n) if n.is_integer() else n for n in sort_orders)
    missing = compute_missing_issues(series.total_issues, sort_orders)

    return templates.TemplateResponse(request, "series_detail.html", {
        "series": series, "present": present, "missing": missing,
    })
