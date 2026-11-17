"""Pantalla de lectura de un tebeo CBZ (BL-LEC1, #824)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import File, Issue, ReadingProgress, Series
from zascarr.services.lector import (
    LectorError,
    guardar_progreso,
    guardar_sentido,
    pagina,
    sentido_de_lectura,
    total_paginas,
)
from zascarr.utils.cover import cached_image_response
from zascarr.web.routes import crear_templates

templates = crear_templates()
router = APIRouter(prefix="/ui/leer", tags=["ui"])


def _error(request: Request, texto: str, status: int = 404) -> HTMLResponse:
    respuesta = templates.TemplateResponse(
        request, "lector_error.html", {"texto": texto}, status_code=status)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/{file_id}", response_class=HTMLResponse)
async def leer(request: Request, file_id: UUID,
               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        return _error(request, "Ese archivo no está disponible para leer.")
    numero = await db.get(Issue, f.issue_id)
    if numero is None:
        return _error(request, "Ese archivo no está vinculado a un número.")
    try:
        total = await total_paginas(db, file_id)
    except LectorError as exc:
        return _error(request, str(exc))
    progreso = (await db.execute(
        select(ReadingProgress).where(ReadingProgress.issue_id == numero.id)
    )).scalar_one_or_none()
    actual = progreso.current_page if progreso is not None else 1
    if actual < 1 or actual > total:
        actual = 1
    serie = await db.get(Series, numero.series_id)
    sentido, origen_sentido = await sentido_de_lectura(db, file_id)
    respuesta = templates.TemplateResponse(request, "lector.html", {
        "archivo": f, "numero": numero, "serie": serie, "total": total,
        "pagina_actual": actual, "sentido": sentido,
        "origen_sentido": origen_sentido,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/{file_id}/pagina/{n}", response_class=Response)
async def pagina_imagen(request: Request, file_id: UUID, n: str,
                        db: AsyncSession = Depends(get_db)) -> Response:
    try:
        numero = int(n)
    except (TypeError, ValueError):
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    try:
        recurso = await pagina(db, file_id, numero)
    except LectorError:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    respuesta = cached_image_response(
        request, recurso.datos, recurso.content_type, recurso.etag)
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


@router.post("/{file_id}/sentido", response_class=Response)
async def cambiar_sentido(file_id: UUID, sentido: str = Form(...),
                          db: AsyncSession = Depends(get_db)) -> Response:
    try:
        await guardar_sentido(db, file_id, sentido)
    except LectorError:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/{file_id}/progreso", response_class=Response)
async def guardar(file_id: UUID, pagina: int = Form(...),
                  db: AsyncSession = Depends(get_db)) -> Response:
    try:
        await guardar_progreso(db, file_id, pagina)
    except LectorError:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
