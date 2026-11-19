"""Lote de revisión de metadatos (CCM-3, #1002).

Pantalla de solo lectura: enseña qué series tienen evidencia recolectada y
cuántas filas de procedencia hay. No construye planes ni escribe.
"""
from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import async_session_factory, get_db
from zascarr.models import EntitySourceRecord, FieldProvenance, Series
from zascarr.services.consolidacion.adaptadores import abrir_adaptadores
from zascarr.services.consolidacion.aplicador import Aplicador, PlanCaducadoError
from zascarr.services.consolidacion.barrida import (
    BLOQUEO_RECOLECCION,
    barrida_en_curso,
    ejecutar_barrida,
    estado_barrida,
    iniciar_barrida,
)
from zascarr.services.consolidacion.consulta import cargar_contexto
from zascarr.services.consolidacion.recolector import Recolector
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()

router = APIRouter(prefix="/ui/datos", tags=["ui"])
templates = crear_templates()


async def _recolectar_en_segundo_plano(limite: int = 20) -> None:
    """Busca fichas de fuentes para series con ID; no aplica metadatos."""
    if barrida_en_curso() or BLOQUEO_RECOLECCION.locked():
        return
    async with BLOQUEO_RECOLECCION:
        abierto = await abrir_adaptadores()
        try:
            async with async_session_factory() as db:
                await Recolector(db, abierto["adaptadores"]).recolectar_lote(limite=limite)
                await db.commit()
        except Exception:  # noqa: BLE001 — una pasada no debe tumbar la app
            logger.exception("ccm.recoleccion_lote_fallida")
        finally:
            await abierto["pila"].aclose()


async def _rellenar_en_segundo_plano(series_ids: list[str]) -> None:
    """Rellena huecos seguros de un lote acotado; no resuelve conflictos."""
    if barrida_en_curso() or BLOQUEO_RECOLECCION.locked():
        return
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
               recolectando: str = Query(default=""), sin_fuentes: str = Query(default=""),
               barrida: str = Query(default=""),
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
        "recolectando": recolectando == "1",
        "sin_fuentes": sin_fuentes == "1",
        "barrida": estado_barrida(),
        "barrida_aviso": barrida == "1",
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/barrida")
async def lanzar_barrida(background: BackgroundTasks) -> RedirectResponse:
    if not iniciar_barrida():
        return RedirectResponse("/ui/datos?barrida=ocupada", status_code=303)
    abierto = await abrir_adaptadores()
    try:
        hay_fuentes = bool(abierto["adaptadores"])
    finally:
        await abierto["pila"].aclose()
    if not hay_fuentes:
        from zascarr.services.consolidacion.barrida import marcar_sin_fuentes
        marcar_sin_fuentes()
        return RedirectResponse("/ui/datos?sin_fuentes=1", status_code=303)
    background.add_task(ejecutar_barrida)
    return RedirectResponse("/ui/datos?barrida=1", status_code=303)


@router.get("/barrida/estado", response_class=HTMLResponse)
async def barrida_estado(request: Request) -> HTMLResponse:
    respuesta = templates.TemplateResponse(
        request, "_barrida_estado.html", {"barrida": estado_barrida()})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/recolectar")
async def recolectar(background: BackgroundTasks) -> RedirectResponse:
    abierto = await abrir_adaptadores()
    try:
        hay_fuentes = bool(abierto["adaptadores"])
    finally:
        await abierto["pila"].aclose()
    if not hay_fuentes:
        return RedirectResponse("/ui/datos?sin_fuentes=1", status_code=303)
    background.add_task(_recolectar_en_segundo_plano, 20)
    return RedirectResponse("/ui/datos?recolectando=1", status_code=303)


@router.post("/rellenar")
async def rellenar(background: BackgroundTasks,
                   db: AsyncSession = Depends(get_db)) -> RedirectResponse:
    ids = (await db.execute(
        select(EntitySourceRecord.entity_id).where(
            EntitySourceRecord.entity_type == "series").distinct().limit(20)
    )).scalars().all()
    background.add_task(_rellenar_en_segundo_plano, [str(x) for x in ids])
    return RedirectResponse("/ui/datos?lanzado=1", status_code=303)
