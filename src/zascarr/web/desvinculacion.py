# ruff: noqa: E501
"""Deshacer la vinculación de un archivo desde la ficha de la serie (BL-R1b, #254): vista previa, confirmación y resultado.

Es la interfaz de `services/desvinculacion.py` (BL-R1a): **no tiene reglas propias**. Enseña lo que calcula el servicio y envía
SOLO el token que ese servicio firmó. Sin JavaScript propio (ADR 0005): la vista previa es una página (un enlace) y la
confirmación un formulario `POST` que funciona sin JS; con htmx la misma confirmación sustituye `#desvinculacion` en su sitio.
Los fallos recuperables se pintan DENTRO de la página con `200` (htmx 4 sustituiría un 4xx, y la persona no ve JSON).

Qué NO hace: no mueve, renombra ni borra el fichero; no vuelve a vincular (eso es otra operación, desde «Por revisar» con el
recorrido de #119/#120); no retira el número que creó la vinculación (D1).
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.api.revision import ejecutar_desvinculacion
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import Series
from zascarr.services.desvinculacion import (
    MENSAJES,
    ArchivoInexistenteError,
    DesvinculacionDeArchivo,
)
from zascarr.services.tokens_revision import (
    MAX_TOKEN_DESVINCULACION,
    TTL_SEGUNDOS,
    verificar_token_desvinculacion,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()
logger = structlog.get_logger()

router = APIRouter(prefix="/ui/series/{series_id}/archivos/{file_id}", tags=["ui"])

#: Cómo se dice, en llano y con la acción, cada fallo que el servicio puede devolver: (título, mensaje, ¿se puede repetir con el mismo token?).
FALLOS: dict[str, tuple[str, str, bool]] = {
    "token_invalido": ("Esta página no es válida", "No se ha cambiado nada: ábrela de nuevo desde la serie.", False),
    "token_caducado": ("Esta página ha caducado", f"Han pasado más de {TTL_SEGUNDOS // 60} minutos. No se ha cambiado nada: ábrela de nuevo para ver el estado actual.", False),
    "resultado_incierto": ("No sabemos si se ha desvinculado", "Se perdió la respuesta al guardar. Pulsa «Comprobar el resultado»: si ya estaba hecho, lo verás; si no, se hará ahora.", True),
    "conflicto_de_bloqueo": ("Ahora no se ha podido", "ZascArr estaba haciendo otra cosa con este archivo. No se ha cambiado nada: vuelve a intentarlo.", True),
    "error_inesperado": ("No se ha podido completar", "No se ha cambiado nada. Vuelve a intentarlo; si se repite, mira «Estado».", False),
}
FALLO_DESCONOCIDO = ("No se ha podido completar", "No se ha cambiado nada que sepamos. Ábrela de nuevo e inténtalo otra vez.", False)

#: Motivos de un resultado `omitido`, con la acción que le queda a la persona.
OMITIDOS: dict[str, str] = {
    "no_vinculado": "Este archivo ya no está vinculado a ningún número, así que no había nada que hacer. Si lo acabas de desvincular, está en «Por revisar».",
    "en_curso": "Ahora mismo ZascArr está trabajando con este archivo. No se ha cambiado nada: prueba de nuevo en unos minutos.",
    "archivo_inexistente": "Este archivo ya no está registrado en ZascArr. No se ha cambiado nada.",
    "cambio_desde_la_vista_previa": "El archivo ha cambiado desde que abriste esta página (por ejemplo, otra pantalla lo vinculó o lo movió). No se ha cambiado nada: ábrela de nuevo para ver cómo está ahora.",
}


def _sin_cache(resp: HTMLResponse) -> HTMLResponse:
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _plantilla(request: Request) -> str:
    """Página completa para quien navega (con o sin JS) y solo el panel para htmx."""
    return "desvinculacion.html" if "hx-request" not in request.headers else "_desvinculacion_panel.html"


async def _serie(db: AsyncSession, series_id: UUID) -> SimpleNamespace:
    """Id y título de la serie como DATOS, no como objeto de la sesión: la confirmación puede revertir la transacción y
    un objeto expirado intentaría releerse (E/S) al pintar la plantilla."""
    fila = (await db.execute(select(Series.id, Series.title).where(Series.id == series_id))).first()
    if fila is None:
        raise HTTPException(status_code=404, detail="Serie no encontrada")
    return SimpleNamespace(id=str(fila.id), title=fila.title)


@router.get("/deshacer", response_class=HTMLResponse)
async def vista_previa(series_id: UUID, file_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Qué pasaría si se deshiciera esta vinculación, SIN hacerlo (solo lectura). Con el token dentro del formulario de confirmar."""
    serie = await _serie(db, series_id)
    try:
        p = await DesvinculacionDeArchivo(db, secret=get_settings().secret_key).previsualizar(file_id)
    except ArchivoInexistenteError:
        raise HTTPException(status_code=404, detail="Ese archivo ya no existe.") from None
    except ValueError:                      # sin clave del servidor para firmar
        raise HTTPException(status_code=503, detail="ZascArr no tiene clave para firmar; reinícialo.") from None
    if p.numero is not None and p.numero.serie_id != str(series_id):
        raise HTTPException(status_code=404, detail="Ese archivo no pertenece a esta serie.")
    return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
        "serie": serie, "file_id": str(file_id), "fase": "vista_previa", "p": p, "r": None, "fallo": None, "token": p.token,
        "textos_bloqueo": MENSAJES}))


@router.post("/deshacer", response_class=HTMLResponse)
async def confirmar(series_id: UUID, file_id: UUID, request: Request,
                    token: str = Form(..., min_length=1, max_length=MAX_TOKEN_DESVINCULACION),
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Confirma con SU token. Es la única acción de esta pantalla que escribe. El token se envía tal cual al servicio."""
    serie = await _serie(db, series_id)
    base = {"serie": serie, "file_id": str(file_id), "fase": "resultado", "p": None, "r": None, "fallo": None, "token": token}
    secreto = get_settings().secret_key
    firmado = verificar_token_desvinculacion(token, secreto, ignorar_caducidad=True) if secreto else None
    # El token es de ESTE archivo y de ESTA serie: una URL no puede aplicar el token de otro.
    if firmado is not None and (firmado.file_id != str(file_id) or firmado.series_id != str(series_id)):
        firmado = None
        token_ajeno = True
    else:
        token_ajeno = False
    if firmado is None:
        titulo, mensaje, repetible = FALLOS["token_invalido"]
        if token_ajeno:
            mensaje = "Esa vista previa es de otro archivo. Abre la de este archivo y confírmala desde ahí. No se ha cambiado nada."
        return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
            **base, "fallo": {"codigo": "token_invalido", "titulo": titulo, "mensaje": mensaje, "repetible": False}}))
    try:
        r = await ejecutar_desvinculacion(db, token)
    except HTTPException as e:
        d = e.detail if isinstance(e.detail, dict) else {"codigo": "error_inesperado"}
        codigo = str(d.get("codigo", "error_inesperado"))
        if codigo not in FALLOS:
            logger.warning("desvinculacion.fallo_sin_texto", codigo=codigo)
        titulo, mensaje, repetible = FALLOS.get(codigo, FALLO_DESCONOCIDO)
        return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
            **base, "fallo": {"codigo": codigo, "titulo": titulo, "mensaje": mensaje, "repetible": repetible}}))
    texto_omitido = None
    if r.resultado == "omitido":
        texto_omitido = OMITIDOS.get(r.motivo or "", r.mensaje)
        if r.motivo not in OMITIDOS:
            logger.warning("desvinculacion.motivo_sin_texto", motivo=r.motivo)
    return _sin_cache(templates.TemplateResponse(request, _plantilla(request), {
        **base, "r": r, "texto_omitido": texto_omitido}))
