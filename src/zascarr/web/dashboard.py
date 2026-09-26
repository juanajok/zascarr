"""
Dashboard de biblioteca — vista principal de ZascArr 1.0 (look-and-feel).

Endpoint GET /ui/ que sirve el dashboard con métricas de colección y últimas
actualizaciones. No añade tablas ni funcionalidad de dominio: solo presenta
datos que ya existen en el modelo (Series, Issues, Files), inspirado en el
brief visual sonarr-comics-template.html.

Métricas:
  - total de series
  - series con al menos un archivo importado
  - total de números conocidos (suma de Series.total_issues)
  - huecos pendientes (suma de missing issues por serie, vía compute_missing_issues)
  - últimas series actualizadas (por el último File.imported_at)

Nota de modelo: File NO tiene series_id — la relación es File → Issue →
Series (File.issue_id → Issue.id → Issue.series_id). Todas las consultas que
cruzan archivos con series pasan por Issue.
"""
from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.api.series import compute_missing_issues
from zascarr.database import get_db
from zascarr.models import File, Issue, Series
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Dashboard principal con métricas de la colección."""
    total_series = (await db.execute(select(func.count(Series.id)))).scalar() or 0

    series_con_archivos = (await db.execute(
        select(func.count(func.distinct(Issue.series_id)))
        .join(File, File.issue_id == Issue.id)
    )).scalar() or 0

    total_issues = (await db.execute(
        select(func.sum(Series.total_issues)).where(Series.total_issues.isnot(None))
    )).scalar() or 0

    issues_importados = (await db.execute(
        select(func.count(func.distinct(File.issue_id))).where(File.issue_id.isnot(None))
    )).scalar() or 0

    porcentaje = round((issues_importados / total_issues * 100) if total_issues else 0)

    # Huecos pendientes: UNA consulta de sort_orders para todas las series
    # (no una query por serie), luego se agrega en Python reusando la misma
    # función de C2 (compute_missing_issues) que usa la ficha de serie.
    series_totales = (await db.execute(
        select(Series.id, Series.total_issues).where(Series.total_issues.isnot(None))
    )).all()

    sort_orders_por_serie: dict = defaultdict(set)
    rows = (await db.execute(
        select(Issue.series_id, Issue.sort_order).where(Issue.sort_order.isnot(None))
    )).all()
    for series_id, sort_order in rows:
        sort_orders_por_serie[series_id].add(float(sort_order))

    huecos_pendientes = 0
    for series_id, total in series_totales:
        huecos_pendientes += len(
            compute_missing_issues(total, sort_orders_por_serie.get(series_id, set()))
        )

    # Últimas series actualizadas: subconsulta con max(imported_at) por serie.
    last_import = (
        select(Issue.series_id.label("series_id"), func.max(File.imported_at).label("ultimo"))
        .join(File, File.issue_id == Issue.id)
        .group_by(Issue.series_id)
        .subquery()
    )
    ultimas_series = (await db.execute(
        select(Series)
        .join(last_import, last_import.c.series_id == Series.id)
        .order_by(last_import.c.ultimo.desc())
        .limit(10)
    )).scalars().all()

    return templates.TemplateResponse(request, "dashboard.html", {
        "total_series": total_series,
        "series_con_archivos": series_con_archivos,
        "porcentaje_completitud": porcentaje,
        "total_issues": total_issues,
        "huecos_pendientes": huecos_pendientes,
        "ultimas_series": ultimas_series,
    })
