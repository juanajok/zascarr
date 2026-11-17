# ruff: noqa: E501
"""«Hacer una copia ahora» (BL-OPS1, ADR 0018) — `POST /ui/copias/pedir` y `GET /ui/copias/estado`.

Router fino: la lógica vive en `services/ops_host.py`. Solo existe bajo `/ui` (nunca `/api/*`: AC-16), sin campos de
formulario (el cuerpo se ignora) y protegido por el Origen/Sesión del middleware existente. Lee solo los ficheros que
escribe el host; no toca la base ni el disco de la biblioteca.

Las zonas del bloque, de fuera adentro: `#copia-anuncio` es la zona `aria-live` y NO se recambia nunca; dentro, `#copia-estado`
es lo único que se sondea (cada 5 s, solo con una copia en marcha); el botón (`#copia-accion`) y el listado (`#copias-lista`)
se actualizan por `hx-swap-oob` cuando cambian, sin sondearlos.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from zascarr.config import get_settings
from zascarr.models import CodigoOps
from zascarr.services import ops_host
from zascarr.services.ops_host import EstadoCopia, VistaCopias
from zascarr.web.routes import crear_templates

templates = crear_templates()
router = APIRouter(tags=["ui"])

ENTRE_COPIAS_MIN = ops_host.ENTRE_COPIAS_S // 60


def _contexto(vista: VistaCopias, copias: list[dict] | None, mensaje_pedir: str = "", con_lista: bool = True,
              oob_accion: bool = False, foco: bool = False) -> dict:
    """`oob_accion`: solo se recambia el botón cuando CAMBIA (htmx no devuelve el foco a un elemento recambiado);
    `foco`: lleva el foco al estado cuando el botón pasa a deshabilitado."""
    return {"v": vista, "copias": copias, "mensaje_pedir": mensaje_pedir, "con_lista": con_lista,
            "oob_accion": oob_accion, "foco": foco, "oob": False}


async def contexto_bloque(settings=None) -> dict:
    """Lo que necesita el bloque completo de `/estado` (la primera vez que se pinta)."""
    settings = settings or get_settings()
    vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
    copias = await asyncio.to_thread(ops_host.leer_copias, settings) if vista.estado != EstadoCopia.NO_ACTIVADO else None
    return _contexto(vista, copias)


def _fragmento(request: Request, contexto: dict) -> HTMLResponse:
    # El fragmento va sin caché: es un estado en vivo.
    respuesta = templates.TemplateResponse(request, "_copias_fragmento.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


async def _fragmento_actual(request: Request, mensaje_pedir: str = "", boton_cambia: bool | None = None) -> HTMLResponse:
    settings = get_settings()
    vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
    # El listado solo se vuelve a pintar cuando no hay copia en marcha: la última respuesta de un sondeo, o tras pedir.
    con_lista = not vista.en_marcha and vista.estado != EstadoCopia.NO_ACTIVADO
    copias = await asyncio.to_thread(ops_host.leer_copias, settings) if con_lista else None
    # Sondeo: el botón ya está deshabilitado mientras hay copia en marcha; solo cambia al terminar.
    cambia = (not vista.en_marcha) if boton_cambia is None else boton_cambia
    return _fragmento(request, _contexto(vista, copias, mensaje_pedir, con_lista=con_lista, oob_accion=cambia))


@router.get("/ui/copias/estado", response_class=HTMLResponse)
async def estado_copias(request: Request) -> HTMLResponse:
    return await _fragmento_actual(request)


@router.post("/ui/copias/pedir", response_class=HTMLResponse)
async def pedir_copia(request: Request) -> HTMLResponse:
    """Pide una copia al auxiliar. Si ya hay una en marcha NO envía nada y devuelve el estado actual (FR-24)."""
    settings = get_settings()
    vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
    if vista.estado == EstadoCopia.NO_ACTIVADO:
        return await _fragmento_actual(request, boton_cambia=True)
    if vista.en_marcha:
        return await _fragmento_actual(request, boton_cambia=False)      # el botón ya estaba deshabilitado
    codigo = await ops_host.pedir_copia(settings)
    if codigo is CodigoOps.ACEPTADA:
        # El auxiliar anota `ops-status.json` antes de contestar; si aun así no se lee, se dice «en marcha» igualmente.
        vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
        if not vista.en_marcha:
            vista = VistaCopias(EstadoCopia.EN_MARCHA, ops_host.MSG_EN_MARCHA, habilitado=False, en_marcha=True)
        return _fragmento(request, _contexto(vista, None, con_lista=False, oob_accion=True, foco=True))
    # Rechazada: el botón sigue habilitado y conserva el foco; el mensaje va a la zona aria-live.
    return await _fragmento_actual(request, ops_host.MENSAJES_PEDIR.get(codigo, ops_host.MENSAJES_PEDIR[CodigoOps.NO_DISPONIBLE]),
                                   boton_cambia=False)
