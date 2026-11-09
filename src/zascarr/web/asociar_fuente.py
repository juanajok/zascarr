"""Asociar otra fuente — entrega A: formulario y comparación de solo lectura (#129)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import MetadataSource, Series
from zascarr.services.asociar_fuente import (
    Comparacion,
    SerieNoEncontradaError,
    comparar,
    normalizar_consulta,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()
router = APIRouter(prefix="/ui/series/{series_id}", tags=["ui"])

_FUENTES = (
    (MetadataSource.COMIC_VINE, "Comic Vine", "1 petición"),
    (MetadataSource.ANILIST, "AniList", "1 petición"),
    (MetadataSource.TEBEOSFERA, "Tebeosfera", "2–8 peticiones (búsqueda y reintentos)"),
    (MetadataSource.GCD, "GCD", "1–3 peticiones (hasta 3 páginas)"),
)
_ATRIBUTO = {
    MetadataSource.COMIC_VINE: "comicvine_enabled",
    MetadataSource.ANILIST: "anilist_enabled",
    MetadataSource.TEBEOSFERA: "tebeosfera_enabled",
    MetadataSource.GCD: "gcd_enabled",
}


def _sin_cache(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


async def _serie(db: AsyncSession, series_id: UUID) -> Series:
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher)).where(Series.id == series_id)
    )).scalar_one_or_none()
    if serie is None:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return serie


def _opciones() -> list[dict]:
    settings = get_settings()
    opciones = []
    for fuente, nombre, coste in _FUENTES:
        disponible = bool(getattr(settings, _ATRIBUTO[fuente]))
        detalle = "Encendida"
        if not disponible:
            detalle = "Apagada en Ajustes"
        elif fuente is MetadataSource.COMIC_VINE and not settings.comicvine_api_key:
            disponible = False
            detalle = "Falta la clave en Ajustes"
        opciones.append({"clave": fuente.value, "nombre": nombre,
                         "disponible": disponible, "detalle": detalle, "coste": coste})
    return opciones


def _contexto(serie: Series, **extra) -> dict:
    return {"serie": serie, "opciones": _opciones(),
            "hay_disponibles": any(o["disponible"] for o in _opciones()), **extra}


@router.get("/asociar", response_class=HTMLResponse)
async def formulario(series_id: UUID, request: Request,
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    return _sin_cache(templates.TemplateResponse(request, "asociar_fuente.html", {
        **_contexto(serie), "q": serie.title}))


@router.post("/asociar/buscar", response_class=HTMLResponse)
async def buscar(series_id: UUID, request: Request,
                 fuente: str = Form(...), q: str = Form(default=""),
                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    try:
        elegida = MetadataSource(fuente)
    except ValueError:
        raise HTTPException(status_code=400, detail="Fuente desconocida") from None
    if elegida not in {f for f, _, _ in _FUENTES}:
        raise HTTPException(status_code=400, detail="Fuente no disponible")
    consulta = normalizar_consulta(q) or normalizar_consulta(serie.title)
    try:
        comparacion: Comparacion = await comparar(db, series_id, elegida, consulta)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    return _sin_cache(templates.TemplateResponse(
        request, "asociar_fuente_resultados.html",
        {**_contexto(serie), "comparacion": comparacion,
         "nombre_fuente": dict((f.value, n) for f, n, _ in _FUENTES)[elegida.value]}))
