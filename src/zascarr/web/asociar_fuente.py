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
from zascarr.services.asociacion_fuente import AsociacionDeFuente, ResultadoAsociacion
from zascarr.services.asociar_fuente import (
    MAX_CONSULTA,
    Comparacion,
    SerieNoEncontradaError,
    SerieSinIdentidadError,
    comparar,
    normalizar_consulta,
    tiene_identidad,
)
from zascarr.services.retirar_asociacion import (
    ResultadoRetirarAsociacion,
    RetirarAsociacionDeFuente,
)
from zascarr.services.tokens_revision import (
    MAX_TOKEN_ASOCIACION,
    MAX_TOKEN_RETIRAR_ASOCIACION,
    verificar_token_asociacion,
)
from zascarr.services.vinculacion import ResultadoInciertoError, VinculacionError
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
            "hay_disponibles": any(o["disponible"] for o in _opciones()),
            "puede_asociar": tiene_identidad(serie), **extra}


@router.get("/asociar", response_class=HTMLResponse)
async def formulario(series_id: UUID, request: Request,
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    return _sin_cache(templates.TemplateResponse(request, "asociar_fuente.html", {
        **_contexto(serie), "q": serie.title, "error_fuente": None}))


@router.post("/asociar/buscar", response_class=HTMLResponse)
async def buscar(series_id: UUID, request: Request,
                 fuente: str = Form(default=""), q: str = Form(default="", max_length=MAX_CONSULTA),
                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    if not tiene_identidad(serie):
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente.html",
            {**_contexto(serie), "q": serie.title, "error_fuente": None}, status_code=409))
    if not fuente:
        # Sin fuente no se consulta ninguna: estado claro en la misma pantalla (no 422 crudo).
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente.html",
            {**_contexto(serie), "q": normalizar_consulta(q) or serie.title,
             "error_fuente": "Elige una web antes de buscar."}, status_code=400))
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
    except SerieSinIdentidadError:
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente.html",
            {**_contexto(serie), "q": serie.title, "error_fuente": None}, status_code=409))
    return _sin_cache(templates.TemplateResponse(
        request, "asociar_fuente_resultados.html",
        {**_contexto(serie), "comparacion": comparacion,
         "nombre_fuente": dict((f.value, n) for f, n, _ in _FUENTES)[elegida.value]}))


@router.post("/asociar/previsualizar", response_class=HTMLResponse)
async def previsualizar(series_id: UUID, request: Request,
                        token: str = Form(..., max_length=MAX_TOKEN_ASOCIACION),
                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Vista previa B1: verifica el token y pinta lo que se guardará; NO escribe."""
    serie = await _serie(db, series_id)
    secreto = get_settings().secret_key
    firmada = (verificar_token_asociacion(token, secreto) if secreto else None)
    error = None
    if firmada is None or firmada.serie_id != str(series_id):
        error = "La propuesta no es válida: vuelve a buscar la ficha."
    elif firmada.entidad != "serie" or firmada.kind == "saga":
        error = "Esa ficha no es una serie y no se puede asociar."
    nombre = (dict((f.value, n) for f, n, _ in _FUENTES).get(firmada.fuente, firmada.fuente)
              if firmada is not None else "")
    return _sin_cache(templates.TemplateResponse(
        request, "asociar_fuente_previsualizar.html",
        {**_contexto(serie), "firmada": firmada, "nombre_fuente": nombre,
         "token": token, "puede_asociar": tiene_identidad(serie), "error": error},
        status_code=400 if error else 200))


@router.post("/asociar/confirmar", response_class=HTMLResponse)
async def confirmar(series_id: UUID, request: Request,
                    token: str = Form(..., max_length=MAX_TOKEN_ASOCIACION),
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """B2: confirma el token; escribe en una transacción y devuelve el resultado."""
    serie = await _serie(db, series_id)
    servicio = AsociacionDeFuente(db, secret=get_settings().secret_key)
    try:
        resultado: ResultadoAsociacion = await servicio.confirmar(token, serie_esperada=series_id)
    except ResultadoInciertoError:
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente_resultado.html",
            {**_contexto(serie), "resultado": None, "incierto": True, "token": token,
             "error": None}, status_code=503))
    except VinculacionError as exc:
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente_resultado.html",
            {**_contexto(serie), "resultado": None, "incierto": False, "token": token,
             "error": str(exc)}, status_code=400))
    return _sin_cache(templates.TemplateResponse(
        request, "asociar_fuente_resultado.html",
        {**_contexto(serie), "resultado": resultado, "incierto": False, "token": token,
         "error": None}))


@router.get("/asociar/{fuente}/retirar", response_class=HTMLResponse)
async def previsualizar_retirada(series_id: UUID, fuente: str, request: Request,
                                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    try:
        elegida = MetadataSource(fuente)
    except ValueError:
        raise HTTPException(status_code=404, detail="Fuente desconocida") from None
    try:
        previa = await RetirarAsociacionDeFuente(
            db, secret=get_settings().secret_key).previsualizar(series_id, elegida)
    except LookupError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    return _sin_cache(templates.TemplateResponse(
        request, "asociar_fuente_retirar.html",
        {**_contexto(serie), "previa": previa,
         "nombre_fuente": dict((f.value, n) for f, n, _ in _FUENTES).get(
             previa.fuente, previa.fuente)}))


@router.post("/asociar/retirar/confirmar", response_class=HTMLResponse)
async def confirmar_retirada(series_id: UUID, request: Request,
                             token: str = Form(..., max_length=MAX_TOKEN_RETIRAR_ASOCIACION),
                             db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    servicio = RetirarAsociacionDeFuente(db, secret=get_settings().secret_key)
    try:
        resultado: ResultadoRetirarAsociacion = await servicio.confirmar(token)
    except ResultadoInciertoError:
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente_retirar_resultado.html",
            {**_contexto(serie), "resultado": None, "incierto": True, "token": token,
             "error": None}, status_code=503))
    except VinculacionError as exc:
        return _sin_cache(templates.TemplateResponse(
            request, "asociar_fuente_retirar_resultado.html",
            {**_contexto(serie), "resultado": None, "incierto": False, "token": token,
             "error": str(exc)}, status_code=400))
    return _sin_cache(templates.TemplateResponse(
        request, "asociar_fuente_retirar_resultado.html",
        {**_contexto(serie), "resultado": resultado, "incierto": False, "token": token,
         "error": None}))
