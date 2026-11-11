# ruff: noqa: E501
"""#341/BL-WK3: página de exportación y descargas CSV en streaming."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

from zascarr.database import async_session_factory
from zascarr.services.exportar import (
    CABECERAS_COLECCION,
    CABECERAS_DESEADOS,
    filas_coleccion,
    filas_deseados,
    generar_csv,
)
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui", tags=["ui"])
templates = crear_templates()


@router.get("/exportar", response_class=HTMLResponse)
async def exportar(request: Request) -> HTMLResponse:
    respuesta = templates.TemplateResponse(request, "exportar.html", {})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _respuesta(filas_factory, cabeceras, nombre: str) -> StreamingResponse:
    async def cuerpo():
        async with async_session_factory() as session:
            async for trozo in generar_csv(filas_factory(session), cabeceras):
                yield trozo

    return StreamingResponse(
        cuerpo(), media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "Cache-Control": "no-store",
        })


@router.get("/exportar/coleccion.csv")
async def exportar_coleccion() -> StreamingResponse:
    return _respuesta(filas_coleccion, CABECERAS_COLECCION, "coleccion-zascarr.csv")


@router.get("/exportar/deseados.csv")
async def exportar_deseados() -> StreamingResponse:
    return _respuesta(filas_deseados, CABECERAS_DESEADOS, "deseados-zascarr.csv")
