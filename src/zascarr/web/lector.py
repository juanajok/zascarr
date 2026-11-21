"""Pantalla de lectura de un tebeo CBZ (BL-LEC1, #824)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import File, Issue, ReadingProgress, ReadingStatus, Series
from zascarr.services.lector import (
    CACHE,
    LectorError,
    es_rar_real,
    guardar_progreso,
    guardar_sentido,
    pagina,
    sentido_de_lectura,
    siguiente_numero,
    total_paginas,
)
from zascarr.services.lectura import marcar
from zascarr.services.legal import is_acknowledged, require_legal_acknowledgment
from zascarr.services.wishlist import WishlistService
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
    if es_rar_real(f):
        estado = await CACHE.preparar(f)
        if estado.estado != "listo":
            failed = estado.estado == "error"
            respuesta = templates.TemplateResponse(request, "lector.html", {
                "archivo": f, "numero": numero, "serie": await db.get(Series, numero.series_id),
                "total": 0, "pagina_actual": 1, "sentido": "ltr",
                "origen_sentido": "tradicion", "preparando": True,
                "error_inicial": estado.motivo or "No se ha podido preparar el tebeo."
                if failed else "",
            }, status_code=404 if failed else 200)
            respuesta.headers["Cache-Control"] = "no-store"
            return respuesta
    try:
        total = await total_paginas(db, file_id)
    except LectorError as exc:
        return _error(request, str(exc))
    progreso = (await db.execute(
        select(ReadingProgress).where(ReadingProgress.issue_id == numero.id)
    )).scalar_one_or_none()
    actual = progreso.current_page if progreso is not None else 1
    # UATP-03 D-4: reanudar en la última si la guardada supera el total; <1, en la primera.
    actual = max(1, min(actual, max(1, total)))
    serie = await db.get(Series, numero.series_id)
    sentido, origen_sentido = await sentido_de_lectura(db, file_id)
    siguiente = await siguiente_numero(db, file_id)
    legal_aceptado = await is_acknowledged(db)
    leido = progreso is not None and progreso.status is ReadingStatus.COMPLETED
    respuesta = templates.TemplateResponse(request, "lector.html", {
        "archivo": f, "numero": numero, "serie": serie, "total": total,
        "pagina_actual": actual, "sentido": sentido,
        "origen_sentido": origen_sentido, "siguiente": siguiente,
        "legal_aceptado": legal_aceptado, "leido": leido,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    return respuesta


def _es_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


@router.post("/{file_id}/leido", response_class=HTMLResponse)
async def marcar_leido_lector(
    request: Request, file_id: UUID,
    operacion: str = Form("marcar"),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Marca o desmarca el número desde la tarjeta de fin (LECUX2).

    La escritura pasa por `services.lectura.marcar`; repetir no duplica el
    estado y deshacer conserva nota y puntuación.
    """
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        return HTMLResponse("Ese archivo no está disponible para leer.", status_code=404)
    numero = await db.get(Issue, f.issue_id)
    if numero is None:
        return HTMLResponse("Ese archivo no está vinculado a un número.", status_code=404)
    if operacion not in ("marcar", "deshacer"):
        return HTMLResponse("Operación no válida.", status_code=400)
    estado = ReadingStatus.COMPLETED if operacion == "marcar" else ReadingStatus.READING
    await marcar(db, numero.id, estado, series_id=numero.series_id)
    if not _es_htmx(request):
        return RedirectResponse(f"/ui/leer/{f.id}", status_code=303)
    siguiente = await siguiente_numero(db, file_id)
    legal_aceptado = await is_acknowledged(db)
    return templates.TemplateResponse(request, "_lector_fin.html", {
        "archivo": f, "numero": numero, "serie": await db.get(Series, numero.series_id),
        "siguiente": siguiente, "legal_aceptado": legal_aceptado,
        "leido": operacion == "marcar",
    }, headers={"Cache-Control": "no-store"})


@router.post("/{file_id}/deseo", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def anadir_a_deseos(file_id: UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None:
        return HTMLResponse("No se ha podido añadir el número.", status_code=404)
    issue = await db.get(Issue, f.issue_id)
    if issue is None:
        return HTMLResponse("No se ha podido añadir el número.", status_code=404)
    await WishlistService(db).add(series_id=issue.series_id)
    await db.commit()
    return HTMLResponse('<p class="aviso">Añadido a Deseados.</p>',
                        headers={"Cache-Control": "no-store"})


@router.get("/{file_id}/estado", response_class=JSONResponse)
async def estado(file_id: UUID, db: AsyncSession = Depends(get_db)) -> JSONResponse:
    f = await db.get(File, file_id)
    if f is None or f.issue_id is None or f.is_missing is True:
        return JSONResponse({"estado": "error", "motivo": "Ese archivo no está disponible."},
                            headers={"Cache-Control": "no-store"})
    if not es_rar_real(f):
        return JSONResponse({"estado": "listo", "motivo": ""},
                            headers={"Cache-Control": "no-store"})
    actual = CACHE.estado(f)
    return JSONResponse({"estado": actual.estado, "motivo": actual.motivo},
                        headers={"Cache-Control": "no-store"})


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
