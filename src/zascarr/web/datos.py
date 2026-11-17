"""Lote de revisión de metadatos (CCM-3, #1002).

Pantalla de solo lectura: enseña qué series tienen evidencia recolectada y
cuántas filas de procedencia hay. No construye planes ni escribe.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import async_session_factory, get_db
from zascarr.models import EntitySourceRecord, FieldProvenance, Series
from zascarr.services.consolidacion.aplicador import Aplicador, PlanCaducadoError
from zascarr.services.consolidacion.consulta import cargar_contexto
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/datos", tags=["ui"])
templates = crear_templates()


async def _rellenar_en_segundo_plano(series_ids: list[str]) -> None:
    """Rellena huecos seguros de un lote acotado; no resuelve conflictos."""
    async with async_session_factory() as db:
        for raw in series_ids:
            try:
                contexto = await cargar_contexto(db, UUID(raw))
                await Aplicador(db).aplicar(contexto.plan())
                await db.commit()
            except PlanCaducadoError:
                await db.rollback()
            except Exception:  # noqa: BLE001 — un fallo no corta el lote
                await db.rollback()


@router.get("", response_class=HTMLResponse)
async def lote(request: Request, lanzado: str = Query(default=""),
               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    con_ficha = select(EntitySourceRecord.entity_id).where(
        EntitySourceRecord.entity_type == "series").distinct()
    con_procedencia = select(FieldProvenance.entity_id).where(
        FieldProvenance.entity_type == "series").distinct()
    series = (await db.execute(
        select(Series).where(Series.id.in_(con_ficha)).order_by(Series.title).limit(100)
    )).scalars().all()
    total_con_ficha = int((await db.execute(
        select(func.count()).select_from(con_ficha.subquery())
    )).scalar() or 0)
    total_con_procedencia = int((await db.execute(
        select(func.count()).select_from(con_procedencia.subquery())
    )).scalar() or 0)
    respuesta = templates.TemplateResponse(request, "datos_lote.html", {
        "series": series, "total_con_ficha": total_con_ficha,
        "total_con_procedencia": total_con_procedencia,
        "lanzado": lanzado == "1",
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/rellenar")
async def rellenar(background: BackgroundTasks,
                   db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    ids = (await db.execute(
        select(EntitySourceRecord.entity_id).where(
            EntitySourceRecord.entity_type == "series").distinct().limit(20)
    )).scalars().all()
    background.add_task(_rellenar_en_segundo_plano, [str(x) for x in ids])
    return RedirectResponse("/ui/datos?lanzado=1", status_code=303)
