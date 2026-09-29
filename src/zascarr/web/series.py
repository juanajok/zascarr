"""
Ficha de serie (C2, ampliada en C1) — /ui/series/{id}.

C2 dejó solo números presentes/ausentes. C1 añade portada (cascada
unificada de 3 niveles, ver docstring de portada() abajo), editorial y
géneros, y un enlace de vuelta a /ui/biblioteca — sigue sin ser el
diseño final de una ficha de serie, solo deja de estar pelada.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.api.series import huecos_de_serie, numeros_poseidos
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import File, Issue, Series, WishlistPolicy
from zascarr.services.orchestrator import MOTIVO_POLITICA_FUTUROS, Orchestrator
from zascarr.utils.cover import (
    cached_image_response,
    extract_cover_thumbnail,
    fetch_and_cache_cover,
    write_cover_cache,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/series", tags=["ui"])

# D8: lo que el selector OFRECE. `todos` no aparece (reservado hasta que D3 le
# dé significado, ver ficha) y `futuros` se pinta deshabilitado con su motivo —
# una opción que parece funcionar y no hace nada es peor que no ofrecerla.
_POLITICAS_OFRECIDAS = {
    WishlistPolicy.NONE: "No buscar nada por mi cuenta",
    WishlistPolicy.MISSING: "Buscar los números que me faltan",
}


async def _contexto_politica(db: AsyncSession, series: Series) -> dict:
    """Lo que la ficha de serie enseña sobre D8, calculado con el MISMO
    predicado que genera (`Orchestrator.querer_de_serie`) — si la página
    recalculara por su cuenta, podría decir una cosa y hacerse otra."""
    return {
        "querer": await Orchestrator(db).querer_de_serie(series),
        "politica_actual": series.wishlist_policy or WishlistPolicy.NONE,
        "politicas_ofrecidas": _POLITICAS_OFRECIDAS,
        "motivo_futuros": MOTIVO_POLITICA_FUTUROS,
    }


@router.get("/{series_id}", response_class=HTMLResponse)
async def detalle(series_id: UUID, request: Request,
                  db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series = (await db.execute(
        select(Series)
        .options(selectinload(Series.publisher), selectinload(Series.genres))
        .where(Series.id == series_id)
    )).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    poseidos = await numeros_poseidos(db, series.id)
    huecos = await huecos_de_serie(db, series, poseidos)

    return templates.TemplateResponse(request, "series_detail.html", {
        "series": series, "present": sorted(poseidos),
        "missing": huecos.faltantes, "huecos": huecos,
        **(await _contexto_politica(db, series)),
    })


@router.post("/{series_id}/politica", response_class=HTMLResponse)
async def cambiar_politica(series_id: UUID, request: Request,
                           wishlist_policy: str = Form(...),
                           db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """D8: el selector de la ficha de serie.

    Mismo blindaje que el resto de escrituras de la UI: el valor del formulario
    se valida contra una lista blanca explícita, nunca se escribe el body tal
    cual. `futuros`/`todos` se rechazan aquí también, no solo ocultos en el
    `<select>` — un formulario manipulado no puede fijar un valor reservado.
    """
    series = (await db.execute(select(Series).where(Series.id == series_id))).scalar_one_or_none()
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    try:
        politica = WishlistPolicy(wishlist_policy)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Política de búsqueda no válida") from exc
    if politica not in _POLITICAS_OFRECIDAS:
        raise HTTPException(
            status_code=422,
            detail="Esa política todavía no se puede aplicar — no hace nada",
        )
    series.wishlist_policy = politica
    await db.flush()
    contexto = await _contexto_politica(db, series)
    return templates.TemplateResponse(
        request, "_politica_serie.html", {"series": series, **contexto}
    )


@router.get("/{series_id}/portada")
async def portada(series_id: UUID, request: Request,
                  db: AsyncSession = Depends(get_db)) -> Response:
    """Cascada unificada de 3 niveles (C1):

    1. ¿Ya está cacheada en disco (venga de donde venga)? Servirla.
    2. Si no, ¿hay algún archivo ya importado de esta serie? Extraer su
       primera página, cachearla, servirla.
    3. Si no, ¿tiene `cover_url` de una fuente externa? Descargarla una
       vez, cachearla, servirla.
    4. Si nada de eso, 404 — el <img> del template cae al placeholder
       CSS (.cover-missing), igual que en pendientes.html.

    Nunca se cachea una AUSENCIA: si no hay portada todavía, la próxima
    petición vuelve a intentarlo (barato: un exists() + una query).
    Todo el trabajo bloqueante (zipfile, Pillow, disco) va a un hilo
    aparte para no congelar el event loop.
    """
    series = await db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=404, detail="Serie no encontrada")

    cache_path = get_settings().covers_cache_path / f"{series_id}.jpg"

    if await asyncio.to_thread(cache_path.exists):
        data = await asyncio.to_thread(cache_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(cache_path))

    # B7 (revisión de PR, 2026-09-26): un File con is_missing=True ya no
    # está en disco — sin este filtro, la portada podía intentar (y
    # fallar) extraer de un CBZ borrado en vez de probar el siguiente
    # número disponible o caer al cover_url externo.
    row = (await db.execute(
        select(File.file_path)
        .join(Issue, File.issue_id == Issue.id)
        .where(Issue.series_id == series_id)
        .where(File.is_missing.is_(False))
        .order_by(Issue.sort_order.asc().nulls_last())
        .limit(1)
    )).first()
    if row:
        result = await asyncio.to_thread(extract_cover_thumbnail, Path(row[0]))
        if result:
            data, content_type = result
            await asyncio.to_thread(write_cover_cache, cache_path, data)
            return cached_image_response(request, data, content_type, _etag_for(cache_path))

    if series.cover_url and await fetch_and_cache_cover(series.cover_url, cache_path):
        data = await asyncio.to_thread(cache_path.read_bytes)
        return cached_image_response(request, data, "image/jpeg", _etag_for(cache_path))

    raise HTTPException(status_code=404, detail="Sin portada disponible")


def _etag_for(path: Path) -> str:
    return f'"{path.stat().st_mtime}"'
