# ruff: noqa: E501
"""Retirar una serie de la biblioteca desde su ficha (BL-SER1, #303)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.api.series import ejecutar_retirada
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import Series
from zascarr.services.borrado_serie import SerieNoEncontradaError
from zascarr.services.retirada_serie import BLOQUEOS, RetiradaDeSerie
from zascarr.services.tokens_revision import (
    MAX_TOKEN_RETIRADA,
    TTL_SEGUNDOS,
    verificar_token_retirada,
)
from zascarr.utils.ruta_visible import ruta_visible
from zascarr.web.routes import crear_templates

templates = crear_templates()
logger = structlog.get_logger()

router = APIRouter(prefix="/ui/series/{series_id}", tags=["ui"])

FALLOS: dict[str, tuple[str, str, bool]] = {
    "token_invalido": ("Esta página no es válida", "No se ha cambiado nada: ábrela de nuevo desde la serie.", False),
    "token_caducado": ("Esta página ha caducado", f"Han pasado más de {TTL_SEGUNDOS // 60} minutos. No se ha cambiado nada: ábrela de nuevo para ver el estado actual.", False),
    "resultado_incierto": ("No sabemos si se ha retirado", "Se perdió la respuesta al guardar. Pulsa «Comprobar el resultado»: si ya estaba hecho, lo verás; si no, se hará ahora.", True),
    "conflicto_de_bloqueo": ("Ahora no se ha podido", "ZascArr estaba haciendo otra cosa con esta serie. No se ha cambiado nada: vuelve a intentarlo.", True),
    "error_inesperado": ("No se ha podido completar", "No se ha cambiado nada. Vuelve a intentarlo; si se repite, mira «Estado».", False),
}
FALLO_DESCONOCIDO = ("No se ha podido completar", "No se ha cambiado nada que sepamos. Ábrela de nuevo e inténtalo otra vez.", False)

OMITIDOS: dict[str, str] = {
    "serie_inexistente": "Esta serie ya no está en tu biblioteca: puede que otra pantalla la retirara o borrara. No se ha cambiado nada más.",
    "en_curso": "Ahora mismo ZascArr está trabajando con esta serie (una asignación de archivos o una búsqueda o descarga). No se ha cambiado nada: prueba de nuevo en unos minutos.",
    "cambio_desde_la_vista_previa": "La serie ha cambiado desde que abriste esta página (por ejemplo, se vinculó otro archivo o empezó una búsqueda). No se ha cambiado nada: ábrela de nuevo para ver cómo está ahora.",
}


def _sin_cache(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _plantilla(request: Request) -> str:
    return "retirada_serie.html" if "hx-request" not in request.headers else "_retirada_panel.html"


async def _serie(db: AsyncSession, series_id: UUID) -> SimpleNamespace:
    fila = (await db.execute(select(Series.id, Series.title).where(Series.id == series_id))).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return SimpleNamespace(id=str(fila.id), title=fila.title, existe=True)


async def _serie_o_none(db: AsyncSession, series_id: UUID) -> SimpleNamespace | None:
    fila = (await db.execute(select(Series.id, Series.title).where(Series.id == series_id))).first()
    return SimpleNamespace(id=str(fila.id), title=fila.title, existe=True) if fila is not None else None


def _archivos(p) -> list[SimpleNamespace]:
    return [SimpleNamespace(id=a.id, nombre=a.nombre, ruta=ruta_visible(a.ruta), numero=a.numero,
                            formato=a.formato, falta_en_disco=a.falta_en_disco, procedencia=a.procedencia)
            for a in (p.archivos if p is not None else [])]


@router.get("/retirar", response_class=HTMLResponse)
async def vista_previa(series_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie(db, series_id)
    try:
        p = await RetiradaDeSerie(db, secret=get_settings().secret_key).previsualizar(series_id)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    except ValueError:
        raise HTTPException(status_code=503, detail="ZascArr no tiene clave para firmar; reinícialo.") from None
    return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
        "serie": serie, "fase": "vista_previa", "p": p, "r": None, "fallo": None, "token": p.token,
        "archivos": _archivos(p), "textos_bloqueo": BLOQUEOS,
        "aviso_disco": p.aviso_disco, "aviso_despues": p.aviso_despues}))


@router.post("/retirar", response_class=HTMLResponse)
async def confirmar(series_id: UUID, request: Request,
                    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_RETIRADA),
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie_o_none(db, series_id)
    base = {"serie": serie, "fase": "resultado", "p": None, "r": None, "fallo": None, "token": token,
            "archivos": [], "textos_bloqueo": BLOQUEOS, "aviso_disco": None, "aviso_despues": None}
    secreto = get_settings().secret_key
    firmado = verificar_token_retirada(token, secreto, ignorar_caducidad=True) if secreto else None
    if firmado is None or firmado.series_id != str(series_id):
        titulo, mensaje, repetible = FALLOS["token_invalido"]
        if firmado is not None:
            mensaje = "Esa vista previa es de otra serie. Abre la de esta serie y confírmala desde ahí. No se ha cambiado nada."
        return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
            **base, "fase": "fallo", "fallo": {"codigo": "token_invalido", "titulo": titulo, "mensaje": mensaje,
                                               "repetible": repetible}}))
    try:
        r = await ejecutar_retirada(db, token)
    except HTTPException as e:
        d = e.detail if isinstance(e.detail, dict) else {"codigo": "error_inesperado"}
        codigo = str(d.get("codigo", "error_inesperado"))
        if codigo not in FALLOS:
            logger.warning("retirada.fallo_sin_texto", codigo=codigo)
        titulo, mensaje, repetible = FALLOS.get(codigo, FALLO_DESCONOCIDO)
        return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
            **base, "fase": "fallo",
            "fallo": {"codigo": codigo, "titulo": titulo, "mensaje": mensaje, "repetible": repetible}}))
    if serie is None and r.titulo:
        serie = SimpleNamespace(id=str(series_id), title=r.titulo, existe=False)
    elif serie is not None and r.resultado == "retirada":
        serie = SimpleNamespace(id=serie.id, title=serie.title, existe=False)
    texto_omitido = None
    if r.resultado == "omitido":
        texto_omitido = OMITIDOS.get(r.motivo or "", r.mensaje)
        if r.motivo not in OMITIDOS:
            logger.warning("retirada.motivo_sin_texto", motivo=r.motivo)
    return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
        **base, "serie": serie, "r": r, "texto_omitido": texto_omitido}))
