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
from zascarr.services.vinculacion import (
    ConflictoDeBloqueoError,
    ResultadoInciertoError,
    TokenCaducadoError,
    TokenInvalidoError,
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
#: Caducado y sin informe: el informe ya se purgó, así que NO se puede afirmar que no se aplicara.
CADUCADO_APLICADO = (
    "Esta página ha caducado",
    f"Han pasado más de {TTL_SEGUNDOS // 60} minutos y ya no se conserva el informe de esta operación. "
    "Puede que la retirada ya se hubiera aplicado: comprueba si la serie sigue en tu biblioteca y si sus "
    "archivos están en «Por revisar». Si la serie sigue ahí, abre la vista previa de nuevo.",
    False,
)
SIN_CLAVE = ("ZascArr no puede firmar ahora",
             "El servidor no tiene clave para firmar; reinícialo y vuelve a intentarlo.", False)

OMITIDOS: dict[str, str] = {
    "serie_inexistente": "Esta serie ya no está en tu biblioteca: puede que otra pantalla la retirara o borrara. No se ha cambiado nada más.",
    "en_curso": "Ahora mismo ZascArr está trabajando con esta serie (una asignación de archivos o una búsqueda o descarga). No se ha cambiado nada: prueba de nuevo en unos minutos.",
    "cambio_desde_la_vista_previa": "La serie ha cambiado desde que abriste esta página (por ejemplo, se vinculó otro archivo, se añadió un número o empezó una asignación o una búsqueda). No se ha cambiado nada: ábrela de nuevo para ver cómo está ahora.",
}


def _sin_cache(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _secreto() -> str:
    secret = get_settings().secret_key
    if not secret:
        raise HTTPException(status_code=503, detail=SIN_CLAVE[1])
    return secret


def _plantilla(request: Request) -> str:
    return "retirada_serie.html" if "hx-request" not in request.headers else "_retirada_panel.html"


def _fallo(request: Request, serie, *, retirar_url: str, codigo: str, titulo: str, mensaje: str,
           repetible: bool, token: str | None = None, status_code: int = 200) -> HTMLResponse:
    return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
        "serie": serie, "fase": "fallo", "p": None, "r": None,
        "fallo": {"codigo": codigo, "titulo": titulo, "mensaje": mensaje, "repetible": repetible},
        "token": token, "retirar_url": retirar_url, "archivos": [], "textos_bloqueo": BLOQUEOS,
        "aviso_disco": None, "aviso_despues": None}, status_code=status_code))


def _sin_clave(request: Request, serie, retirar_url: str, token: str | None = None) -> HTMLResponse:
    return _fallo(request, serie, retirar_url=retirar_url, codigo="sin_clave", titulo=SIN_CLAVE[0],
                  mensaje=SIN_CLAVE[1], repetible=False, token=token, status_code=503)


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
    retirar_url = f"/ui/series/{series_id}/retirar"
    try:
        p = await RetiradaDeSerie(db, secret=_secreto()).previsualizar(series_id)
    except SerieNoEncontradaError:
        raise HTTPException(status_code=404, detail="Serie no encontrada") from None
    except HTTPException as e:
        if e.status_code == 503:
            return _sin_clave(request, serie, retirar_url)
        raise
    return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
        "serie": serie, "fase": "vista_previa", "p": p, "r": None, "fallo": None, "token": p.token,
        "retirar_url": retirar_url, "archivos": _archivos(p), "textos_bloqueo": BLOQUEOS,
        "aviso_disco": p.aviso_disco, "aviso_despues": p.aviso_despues}))


@router.post("/retirar", response_class=HTMLResponse)
async def confirmar(series_id: UUID, request: Request,
                    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_RETIRADA),
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    serie = await _serie_o_none(db, series_id)
    retirar_url = f"/ui/series/{series_id}/retirar"
    try:
        firmado = verificar_token_retirada(token, _secreto(), ignorar_caducidad=True)
    except HTTPException as e:
        if e.status_code == 503:
            return _sin_clave(request, serie, retirar_url, token)
        raise
    if firmado is None or firmado.series_id != str(series_id):
        titulo, mensaje, repetible = FALLOS["token_invalido"]
        if firmado is not None:
            mensaje = "Esa vista previa es de otra serie. Abre la de esta serie y confírmala desde ahí. No se ha cambiado nada."
        return _fallo(request, serie, retirar_url=retirar_url, codigo="token_invalido", titulo=titulo,
                      mensaje=mensaje, repetible=repetible, token=token)
    try:
        r = await RetiradaDeSerie(db, secret=_secreto()).confirmar(token)
    except TokenInvalidoError:
        titulo, mensaje, repetible = FALLOS["token_invalido"]
        return _fallo(request, serie, retirar_url=retirar_url, codigo="token_invalido", titulo=titulo,
                      mensaje=mensaje, repetible=repetible, token=token)
    except TokenCaducadoError as e:
        titulo, mensaje, repetible = CADUCADO_APLICADO if e.puede_haberse_aplicado else FALLOS["token_caducado"]
        return _fallo(request, serie, retirar_url=retirar_url, codigo="token_caducado", titulo=titulo,
                      mensaje=mensaje, repetible=repetible, token=token)
    except ConflictoDeBloqueoError:
        titulo, mensaje, repetible = FALLOS["conflicto_de_bloqueo"]
        return _fallo(request, serie, retirar_url=retirar_url, codigo="conflicto_de_bloqueo", titulo=titulo,
                      mensaje=mensaje, repetible=repetible, token=token)
    except ResultadoInciertoError:
        titulo, mensaje, repetible = FALLOS["resultado_incierto"]
        return _fallo(request, serie, retirar_url=retirar_url, codigo="resultado_incierto", titulo=titulo,
                      mensaje=mensaje, repetible=repetible, token=token)
    except HTTPException as e:
        if e.status_code == 503:
            return _sin_clave(request, serie, retirar_url, token)
        raise
    except Exception:
        logger.exception("retirada.error_inesperado_ui")
        titulo, mensaje, repetible = FALLOS["error_inesperado"]
        return _fallo(request, serie, retirar_url=retirar_url, codigo="error_inesperado", titulo=titulo,
                      mensaje=mensaje, repetible=repetible, token=token)
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
        "serie": serie, "fase": "resultado", "p": None, "r": r, "fallo": None, "token": token,
        "retirar_url": retirar_url, "archivos": [], "textos_bloqueo": BLOQUEOS, "aviso_disco": None, "aviso_despues": None,
        "texto_omitido": texto_omitido}))
