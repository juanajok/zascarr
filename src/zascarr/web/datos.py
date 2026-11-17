"""Lote de revisión de metadatos (CCM-3, #1002).

Pantalla de solo lectura: enseña qué series tienen evidencia recolectada y
cuántas filas de procedencia hay. No construye planes ni escribe.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import EntitySourceRecord, FieldProvenance, Series
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/datos", tags=["ui"])
templates = crear_templates()


@router.get("", response_class=HTMLResponse)
async def lote(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
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
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
