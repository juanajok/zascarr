"""
Router de descubrimiento de series (C0) — /ui/descubrir.

Busca en fuentes externas (Comic Vine/AniList/Tebeosfera, vía
DiscoveryService) y da de alta la `Series` local que Wishlist y el
matcher necesitan para funcionar — ver el docstring de
services/discovery.py para el porqué. Dar de alta una serie es
catalogar metadatos, no descargar nada: a diferencia de
`/ui/wishlist/anadir`, esta ruta NO lleva `require_legal_acknowledgment`.
"""
from __future__ import annotations

import asyncio
import hashlib
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.discovery import DiscoveryService
from zascarr.utils.cover import cached_image_response, fetch_and_cache_cover
from zascarr.web.library import _TRADICION_LABEL
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/descubrir", tags=["ui"])

# Portadas de RESULTADOS de búsqueda (aún sin Series creada, así que no
# hay /ui/series/{id}/portada al que apuntar). Este proxy es la única
# forma segura de mostrarlas sin hotlinkear el navegador directo al CDN
# externo (regla permanente, §3.1.4) — pero a diferencia del cascade de
# portadas ya existente, la URL la elige la petición, no la BD, así que
# hace falta una lista blanca de host por fuente: sin ella, este
# endpoint sería un proxy abierto de imágenes arbitrarias (SSRF real,
# no teórico — cualquiera podría usarlo para sondear red interna).
# Comic Vine: dominio de imagen no verificado en vivo todavía (sin
# COMICVINE_API_KEY a mano en esta sesión) — se permiten los dos
# dominios documentados/conocidos de CBS Interactive; revisar si
# alguna vez se ve un 400 real con una key configurada.
_ALLOWED_COVER_HOSTS: dict[MetadataSource, tuple[str, ...]] = {
    MetadataSource.COMIC_VINE: ("comicvine.gamespot.com", "cbsistatic.com"),
    MetadataSource.ANILIST: ("anilist.co",),
    MetadataSource.TEBEOSFERA: ("tebeosfera.com",),
    MetadataSource.GCD: ("comics.org",),
}


def _cover_host_allowed(url: str, source: MetadataSource) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    if not host:
        return False
    return any(
        host == dominio or host.endswith(f".{dominio}")
        for dominio in _ALLOWED_COVER_HOSTS.get(source, ())
    )


@router.get("", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "descubrir.html", {})


@router.get("/buscar", response_class=HTMLResponse)
async def buscar(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    resultados, avisos = await DiscoveryService(db).search(q)
    tradiciones = [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition]
    return templates.TemplateResponse(
        request, "_resultados_descubrir.html",
        {"resultados": resultados, "avisos": avisos, "tradiciones": tradiciones},
    )


@router.get("/portada")
async def portada(request: Request, url: str, source: MetadataSource):
    """Portada de un candidato de búsqueda, antes de que exista una
    Series — bug real, reportado ("¿puede tener algo así como el
    pantallazo [de Sonarr]?"). Caché en disco por hash de la URL
    (content-addressed: no hay series_id todavía), mismas cabeceras
    de caché que el resto de portadas de la app."""
    if not _cover_host_allowed(url, source):
        raise HTTPException(status_code=400, detail="Host de portada no permitido")

    clave = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
    cache_path = get_settings().covers_cache_path / "descubrir" / f"{clave}.jpg"

    if not await asyncio.to_thread(cache_path.exists):
        if not await fetch_and_cache_cover(url, cache_path):
            raise HTTPException(status_code=404, detail="Sin portada disponible")

    data = await asyncio.to_thread(cache_path.read_bytes)
    return cached_image_response(request, data, "image/jpeg", clave)


@router.post("/crear", response_class=HTMLResponse)
async def crear(
    request: Request,
    source: MetadataSource = Form(...),
    external_id: str = Form(...),
    title: str = Form(...),
    tradition: ComicTradition = Form(...),
    start_year: int | None = Form(default=None),
    description: str | None = Form(default=None),
    cover_url: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    try:
        series, creada = await DiscoveryService(db).get_or_create_series(
            source=source, external_id=external_id, title=title,
            tradition=tradition, start_year=start_year,
            description=description, cover_url=cover_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request, "_serie_creada.html", {"series": series, "creada": creada}
    )
