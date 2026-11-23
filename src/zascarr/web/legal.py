"""
Aviso legal — /ui/legal (wizard de aceptación) y /legal (texto completo,
solo lectura). Ninguna de las dos rutas lleva
Depends(require_legal_acknowledgment): tienen que ser alcanzables
precisamente para poder aceptar el aviso o simplemente leerlo.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.legal import (
    RETORNO_LEGAL_POR_DEFECTO,
    acknowledge,
    current_legal_version,
    get_acknowledgment,
    render_legal_html,
    resolver_destino_legal,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(tags=["ui"])

_UUID = (r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
         r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_RUTA_NUMERO = re.compile(rf"/ui/series/{_UUID}/numero/{_UUID}")
_RUTA_SERIE = re.compile(rf"/ui/series/{_UUID}")
_RUTA_LECTOR = re.compile(rf"/ui/leer/{_UUID}")


def con_aviso_legal(destino: str) -> str:
    """Destino local con la señal de un solo uso que pinta el aviso al llegar."""
    partes = urlsplit(destino)
    pares = [(clave, valor) for clave, valor in parse_qsl(
        partes.query, keep_blank_values=True) if clave != "aviso_legal"]
    pares.append(("aviso_legal", "aceptado"))
    return urlunsplit((partes.scheme, partes.netloc, partes.path,
                       urlencode(pares), partes.fragment))


def etiqueta_de_vuelta(destino: str) -> str:
    """Nombre llano del destino, con preposición para «Volver a…» y el aviso."""
    ruta = urlsplit(destino).path
    if ruta == "/ui/wishlist":
        return "a Deseados"
    if ruta == "/ui/mejoras":
        return "a Mejoras"
    if ruta == "/ui/descubrir" or ruta.startswith("/ui/descubrir/"):
        return "a Descubrir"
    if _RUTA_NUMERO.fullmatch(ruta):
        return "al número"
    if _RUTA_SERIE.fullmatch(ruta):
        return "a la serie"
    if _RUTA_LECTOR.fullmatch(ruta):
        return "al lector"
    return "a la biblioteca"


@router.get("/ui/legal", response_class=HTMLResponse)
async def wizard(request: Request, volver: str = Query(default=""),
                 falta: str = Query(default=""),
                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    ack = await get_acknowledgment(db)
    destino = resolver_destino_legal(request, volver)
    respuesta = templates.TemplateResponse(request, "legal_wizard.html", {
        "accepted": ack is not None,
        "accepted_at": ack.accepted_at if ack else None,
        "legal_version": current_legal_version(),
        "volver": destino or RETORNO_LEGAL_POR_DEFECTO,
        "volver_etiqueta": etiqueta_de_vuelta(
            destino or RETORNO_LEGAL_POR_DEFECTO),
        "falta": falta == "1",
        # Solo se promete conservar el destino si de verdad se conservó: si
        # ningún candidato valía, ya se cayó al respaldo antes de pintar el aviso.
        "destino_conservado": destino is not None,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/ui/legal/accept")
async def accept(
    request: Request,
    acepto_1: bool = Form(default=False), acepto_2: bool = Form(default=False),
    acepto_3: bool = Form(default=False), volver: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    destino = resolver_destino_legal(request, volver)
    if not (acepto_1 and acepto_2 and acepto_3):
        falta = "/ui/legal?falta=1"
        if destino is not None:
            falta = f"/ui/legal?volver={quote(destino, safe='')}&falta=1"
        return RedirectResponse(falta, status_code=303,
                                headers={"Cache-Control": "no-store"})
    await acknowledge(db)
    llegada = con_aviso_legal(destino or RETORNO_LEGAL_POR_DEFECTO)
    return RedirectResponse(llegada, status_code=303,
                            headers={"Cache-Control": "no-store"})


@router.get("/legal", response_class=HTMLResponse)
async def full_text(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "legal_full.html", {"legal_html": render_legal_html()}
    )
