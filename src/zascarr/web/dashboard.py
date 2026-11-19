"""
Inicio de biblioteca — vista principal de ZascArr (GET /ui/).

Router fino: el estado sale de `services/inicio.py` (V4), no se calcula aquí ni en la plantilla.
No añade tablas ni funcionalidad de dominio.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services import logs_persistidos
from zascarr.services.inicio import cargar_inicio
from zascarr.services.primeros_pasos import fecha_llana
from zascarr.utils.registro_reciente import texto_reciente
from zascarr.web.routes import crear_templates

templates = crear_templates()
templates.env.filters["fecha_llana"] = fecha_llana

router = APIRouter(prefix="/ui", tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Inicio: primeros pasos derivados del estado y las cifras de la colección."""
    vista = await cargar_inicio(db)
    return templates.TemplateResponse(request, "dashboard.html", {"v": vista})


def _descarga(contenido: str, ahora: str) -> Response:
    return Response(
        content=contenido,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="zascarr-logs-{ahora}.txt"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/logs")
async def descargar_logs(
    fecha: str = Query(default=""), hora: str = Query(default=""),
    evento: str = Query(default=""), limite: int = Query(default=1000, ge=1, le=1000),
) -> Response:
    """Descarga logs filtrados del fichero rotado; si no hay, usa el búfer.

    Sin filtros y sin ficheros persistidos se conserva el contrato de BL-E5
    (últimos eventos en memoria). Con filtros se devuelve JSONL, apto para
    adjuntar a una incidencia sin exponer rutas ni secretos.
    """
    ahora = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    filtros = bool(fecha or hora or evento)
    hay_ficheros = bool(await asyncio.to_thread(logs_persistidos.dias_disponibles))
    if filtros or hay_ficheros:
        eventos = await asyncio.to_thread(
            logs_persistidos.leer_eventos, fecha=fecha, hora=hora,
            evento=evento, limite=limite)
        if not eventos:
            return _descarga("No hay registros para esos filtros.\n", ahora)
        return _descarga(logs_persistidos.texto_jsonl(eventos), ahora)
    return _descarga(texto_reciente(), ahora)


@router.get("/logs/visor", response_class=HTMLResponse)
async def visor_logs(
    request: Request, fecha: str = Query(default=""), hora: str = Query(default=""),
    evento: str = Query(default=""),
) -> HTMLResponse:
    """Pantalla para elegir fecha/hora/evento y descargar el subconjunto."""
    dias = await asyncio.to_thread(logs_persistidos.dias_disponibles)
    eventos_disponibles = await asyncio.to_thread(
        logs_persistidos.eventos_disponibles, fecha=fecha)
    filas = []
    if dias:
        filas = await asyncio.to_thread(
            logs_persistidos.leer_eventos, fecha=fecha, hora=hora,
            evento=evento, limite=300)
    return templates.TemplateResponse(request, "_logs_visor.html", {
        "dias": dias, "eventos": eventos_disponibles, "filas": filas,
        "fecha": fecha, "hora": hora, "evento": evento,
        "sin_ficheros": not dias,
    })
