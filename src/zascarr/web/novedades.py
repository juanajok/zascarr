"""Pantalla y API de Novedades semanales (D5, v1 USA/Comic Vine)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.novedades import (
    NovedadesApagadaError,
    NovedadesError,
    cargar_semana,
    etiqueta_dia,
    etiqueta_semana,
    filtrar_editorial,
    semana_iso,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/novedades", tags=["ui"])
api_router = APIRouter(prefix="/api/novedades", tags=["api"])


@router.get("", response_class=HTMLResponse)
async def novedades(
    request: Request,
    semana: str | None = Query(default=None),
    editorial: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    hoy = date.today()
    inicio = semana_iso(semana, hoy=hoy)
    error = None
    apagada = False
    completa = None
    try:
        completa = await cargar_semana(db, inicio, hoy=hoy)
    except NovedadesApagadaError as exc:
        apagada = True
        error = str(exc)
    except NovedadesError as exc:
        error = str(exc)
    visible = filtrar_editorial(completa, editorial) if completa else None
    contexto = {
        "hoy": hoy,
        "inicio": inicio,
        "semana": visible,
        "editorial": editorial or "",
        "editoriales": completa.editoriales if completa else [],
        "error": error,
        "apagada": apagada,
        "etiqueta_semana": etiqueta_semana(inicio),
        "etiqueta_dia": etiqueta_dia,
        "anterior": (inicio - timedelta(days=7)).isoformat(),
        "siguiente": (inicio + timedelta(days=7)).isoformat(),
    }
    respuesta = templates.TemplateResponse(request, "novedades.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@api_router.get("")
async def novedades_api(
    response: Response,
    semana: str | None = Query(default=None),
    editorial: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    inicio = semana_iso(semana)
    try:
        completa = await cargar_semana(db, inicio)
    except NovedadesApagadaError as exc:
        raise HTTPException(status_code=503, detail=str(exc),
                            headers={"Cache-Control": "no-store"}) from exc
    except NovedadesError as exc:
        raise HTTPException(status_code=503, detail=str(exc),
                            headers={"Cache-Control": "no-store"}) from exc
    visible = filtrar_editorial(completa, editorial)
    return {
        "semana": {"inicio": visible.inicio.isoformat(), "fin": visible.fin.isoformat()},
        "total": visible.total,
        "interesantes": visible.interesantes,
        "items": [
            {**asdict(n), "fecha": n.fecha.isoformat(),
             "series_id": str(n.series_id) if n.series_id else None}
            for n in visible.novedades
        ],
    }
