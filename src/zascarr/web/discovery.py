# ruff: noqa: E501
"""
Router de descubrimiento de series (C0) — /ui/descubrir.

Busca en fuentes externas (Comic Vine/AniList/Tebeosfera, vía DiscoveryService) y da de alta la `Series` local que
Wishlist y el matcher necesitan para funcionar. Dar de alta una serie es catalogar metadatos, no descargar nada: a
diferencia de `/ui/wishlist/anadir`, estas rutas NO llevan `require_legal_acknowledgment`.

La creación es en DOS PASOS y delega en `AltaDeSerie` (I2 de #114; ADR 0008 §2, ADR 0010 P-1): **Revisar** (vista previa,
no escribe nada) y **Crear** (confirmación con el token de la vista previa). El navegador nunca aporta los datos de la serie:
reenvía el token que el servidor firmó al buscar y la tradición que elige la persona.
"""
from __future__ import annotations

import asyncio
import hashlib
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import ComicTradition, MetadataSource
from zascarr.services.alta_serie import (
    AltaDeSerie,
    AltaError,
    NoSePuedeDeshacerError,
    ParecidasNuevasError,
)
from zascarr.services.descubrimiento_libre import firmar_resultados
from zascarr.services.discovery import DiscoveryService
from zascarr.services.tokens_revision import MAX_TOKEN_ALTA, MAX_TOKEN_CANDIDATA_SIN_GRUPO
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
async def index(request: Request, q: str = Query(default="", max_length=200)) -> HTMLResponse:
    """`?q=` (V4: «Buscar una serie» del Inicio) prellena la caja y lanza la búsqueda al cargar."""
    return templates.TemplateResponse(request, "descubrir.html", {"q": q.strip()})


def _tradiciones() -> list[tuple[str, str]]:
    return [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition]


def _fragmento_sin_clave(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "_alta_error.html",
        {"texto": "ZascArr no tiene clave para firmar lo que ves: reinícialo e inténtalo de nuevo."})


@router.get("/buscar", response_class=HTMLResponse)
async def buscar(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    resultados, avisos = await DiscoveryService(db).search(q)
    secreto = get_settings().secret_key
    if not secreto:
        return _fragmento_sin_clave(request)
    firmados, omitidas = firmar_resultados(resultados, secreto)
    avisos = list(avisos)
    if omitidas:
        avisos.append(f"Se han omitido {omitidas} resultado(s) cuyo título o identificador no se puede guardar.")
    return templates.TemplateResponse(
        request, "_resultados_descubrir.html",
        {"resultados": firmados, "avisos": avisos, "tradiciones": _tradiciones(), "hay_resultados": bool(resultados)},
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


def _servicio(db: AsyncSession) -> AltaDeSerie | None:
    secreto = get_settings().secret_key
    return AltaDeSerie(db, secret=secreto) if secreto else None


#: Los `AltaError` cuyo mensaje YA está escrito para la persona. Cualquier otro código (o una excepción base) no muestra su
#: texto —podría ser un identificador, un UUID o un detalle interno—: sale el mensaje de reserva.
_CODIGOS_CON_MENSAJE_PROPIO = frozenset({
    "token_invalido", "datos_invalidos", "decision_invalida", "demasiadas_parecidas", "la_serie_ya_no_existe",
    "identificador_cambiado", "alta_deshecha", "alta_serie_ausente",
})
_MENSAJES_POR_CODIGO = {
    "serie_no_encontrada": "La serie ya no está en tu biblioteca; no hay nada que deshacer.",
}
_MENSAJE_DE_RESERVA = "No se ha podido completar la operación. Vuelve a buscar el título e inténtalo de nuevo."


def _texto_de(exc: AltaError) -> str:
    codigo = getattr(exc, "codigo", "")
    if codigo in _MENSAJES_POR_CODIGO:
        return _MENSAJES_POR_CODIGO[codigo]
    return str(exc) if codigo in _CODIGOS_CON_MENSAJE_PROPIO else _MENSAJE_DE_RESERVA


def _error(request: Request, texto: str, **extra) -> HTMLResponse:
    """Los fallos recuperables se pintan DENTRO de la tarjeta (con 200): htmx no sustituye una respuesta 4xx."""
    return templates.TemplateResponse(request, "_alta_error.html", {"texto": texto, **extra})


@router.post("/revisar", response_class=HTMLResponse)
async def revisar(
    request: Request,
    candidata: str = Form(..., min_length=1, max_length=MAX_TOKEN_CANDIDATA_SIN_GRUPO),
    tradition: ComicTradition = Form(...),
    decision: Literal["reutilizar", "crear_igualmente"] | None = Form(default=None),
    serie_id: UUID | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Paso 1: la vista previa de lo que pasaría. NO escribe nada. La tradición la elige la persona (sin valor por defecto)."""
    servicio = _servicio(db)
    if servicio is None:
        return _fragmento_sin_clave(request)
    try:
        vista = await servicio.previsualizar_sin_grupo(
            tradicion=tradition, candidata=candidata, decision=decision, serie_id=serie_id)
    except AltaError as exc:
        return _error(request, _texto_de(exc))
    return templates.TemplateResponse(request, "_alta_vista_previa.html", {
        "vista": vista, "candidata": candidata, "tradicion": tradition.value,
        "tradicion_etiqueta": _TRADICION_LABEL[tradition], "tradiciones": _tradiciones(),
    })


@router.post("/crear", response_class=HTMLResponse)
async def crear(
    request: Request,
    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_ALTA),
    candidata: str | None = Form(default=None, max_length=MAX_TOKEN_CANDIDATA_SIN_GRUPO),
    tradition: ComicTradition | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Paso 2: ejecuta EXACTAMENTE lo que enseñó la vista previa (solo el token). Ya no acepta los datos de la serie."""
    servicio = _servicio(db)
    if servicio is None:
        return _fragmento_sin_clave(request)
    try:
        resultado = await servicio.confirmar(token)
    except ParecidasNuevasError as exc:
        return _error(request, "Han aparecido series parecidas desde la vista previa: revísalas y decide de nuevo.",
                      parecidas=exc.nuevas, candidata=candidata, tradicion=tradition.value if tradition else None,
                      tradiciones=_tradiciones())
    except AltaError as exc:
        return _error(request, _texto_de(exc))
    return templates.TemplateResponse(request, "_alta_resultado.html", {"r": resultado})


_MOTIVOS_DE_NO_DESHACER = {
    "no_creada_por_esta_operacion": "Esa serie no la creó esta operación, así que no se puede deshacer desde aquí.",
    "tiene_archivos": "La serie ya tiene archivos vinculados, así que no se puede deshacer.",
    "tiene_numeros": "La serie ya tiene números, así que no se puede deshacer.",
    "operacion_viva": "La serie tiene una operación en curso: espera a que termine.",
    "tiene_deseados": "La serie ya tiene deseados o una política de búsqueda, así que no se puede deshacer.",
}


@router.post("/deshacer", response_class=HTMLResponse)
async def deshacer(
    request: Request, series_id: UUID = Form(...), operacion_id: UUID = Form(...),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Deshace el alta SOLO si la creó esa operación y nada depende de la serie (lo comprueba el servicio)."""
    servicio = _servicio(db)
    if servicio is None:
        return _fragmento_sin_clave(request)
    try:
        hecho = await servicio.deshacer(series_id, operacion_id)
    except NoSePuedeDeshacerError as exc:
        return _error(request, _MOTIVOS_DE_NO_DESHACER.get(exc.motivo, "No se puede deshacer."))
    except AltaError as exc:
        return _error(request, _texto_de(exc))
    return templates.TemplateResponse(request, "_alta_deshecha.html", {"hecho": hecho})
