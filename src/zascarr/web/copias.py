# ruff: noqa: E501
"""«Hacer una copia ahora» (BL-OPS1, ADR 0021) — `POST /ui/copias/pedir` y `GET /ui/copias/estado`.

Router fino: la lógica vive en `services/ops_host.py`. Solo existe bajo `/ui` (nunca `/api/*`: AC-16), sin campos de
formulario (el cuerpo se ignora) y protegido por el Origen/Sesión del middleware existente. Lee solo los ficheros que
escribe el host; no toca la base ni el disco de la biblioteca.

Las zonas del bloque, de fuera adentro: `#copia-anuncio` es la zona `aria-live` y NO se recambia nunca; dentro, `#copia-estado`
es lo único que se sondea (cada 5 s, solo con una copia en marcha); el botón (`#copia-accion`) y el listado (`#copias-lista`)
se actualizan por `hx-swap-oob` cuando cambian, sin sondearlos.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import CodigoOps
from zascarr.services import ops_host, restauracion, tareas
from zascarr.services.ops_host import EstadoCopia, VistaCopias
from zascarr.web.routes import crear_templates

templates = crear_templates()
router = APIRouter(tags=["ui"])

ENTRE_COPIAS_MIN = ops_host.ENTRE_COPIAS_S // 60
_tarea_copia = None


MSG_RESTAURACION_EN_MARCHA = "Hay una restauración en marcha. Cuando termine podrás hacer copias."


def _contexto(vista: VistaCopias, copias: list[dict] | None, mensaje_pedir: str = "", con_lista: bool = True,
              oob_accion: bool = False, foco: bool = False, vr=None, restaurando: bool = False) -> dict:
    """`oob_accion`: solo se recambia el botón cuando CAMBIA (htmx no devuelve el foco a un elemento recambiado);
    `foco`: lleva el foco al estado cuando el botón pasa a deshabilitado. `vr`/`restaurando` son el estado de la
    restauración (BL-OPS2): mientras corre no hay botones «Restaurar…» ni se piden copias (FR-29/AC-21)."""
    if restaurando and vista.boton:
        vista = VistaCopias(vista.estado, MSG_RESTAURACION_EN_MARCHA, vista.detalle, boton=True,
                            habilitado=False, en_marcha=vista.en_marcha, nivel="amber",
                            nocturna_omitida=vista.nocturna_omitida, extra=vista.extra)
    if copias is not None:
        copias = [c for c in copias if c.get("restaurable") is True]
    return {"v": vista, "copias": copias, "mensaje_pedir": mensaje_pedir, "con_lista": con_lista,
            "oob_accion": oob_accion, "foco": foco, "oob": False, "vr": vr, "restaurando": restaurando,
            "version_llana": ops_host.version_llana, "fecha_absoluta": ops_host.fecha_absoluta}


async def contexto_bloque(settings=None, revision_actual: str | None = None) -> dict:
    """Lo que necesita el bloque completo de `/estado` (la primera vez que se pinta)."""
    settings = settings or get_settings()
    vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
    vr = await asyncio.to_thread(ops_host.resolver_restauracion, settings)
    restaurando = vr.en_marcha
    copias = await asyncio.to_thread(ops_host.leer_copias, settings) if vista.estado != EstadoCopia.NO_ACTIVADO else None
    copias = restauracion.ofrecer(copias, revision_actual, settings.auth_mode,
                                  permitir=not (vista.en_marcha or restaurando))
    return _contexto(vista, copias, vr=vr, restaurando=restaurando)


def _fragmento(request: Request, contexto: dict) -> HTMLResponse:
    # El fragmento va sin caché: es un estado en vivo.
    respuesta = templates.TemplateResponse(request, "_copias_fragmento.html", contexto)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


async def _fragmento_actual(request: Request, mensaje_pedir: str = "", boton_cambia: bool | None = None) -> HTMLResponse:
    global _tarea_copia
    settings = get_settings()
    vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
    vr = await asyncio.to_thread(ops_host.resolver_restauracion, settings)
    restaurando = vr.en_marcha
    if vista.en_marcha and _tarea_copia is None:
        _tarea_copia = tareas.iniciar_copia()
    elif not vista.en_marcha and _tarea_copia is not None:
        if vista.estado in (EstadoCopia.HECHA, EstadoCopia.DIARIO):
            tareas.terminar(_tarea_copia.id, resumen="Copia terminada")
        else:
            tareas.error(_tarea_copia.id,
                         tipo_error="copia_" + str(vista.estado))
        _tarea_copia = None
    # El listado solo se vuelve a pintar cuando no hay copia en marcha: la última respuesta de un sondeo, o tras pedir.
    con_lista = not vista.en_marcha and vista.estado != EstadoCopia.NO_ACTIVADO
    copias = await asyncio.to_thread(ops_host.leer_copias, settings) if con_lista else None
    if copias is not None and settings.auth_mode != "none":
        from zascarr.database import async_session_factory
        from zascarr.services.restauracion import revision_actual
        async with async_session_factory() as db:
            revision = await revision_actual(db)
        copias = restauracion.ofrecer(
            copias, revision, settings.auth_mode,
            permitir=not (vista.en_marcha or restaurando))
    # Sondeo: el botón ya está deshabilitado mientras hay copia en marcha; solo cambia al terminar. Con una
    # restauración en marcha también se sondea (para volver a ofrecer las acciones al terminar).
    cambia = (not vista.en_marcha and not restaurando) if boton_cambia is None else boton_cambia
    if restaurando:
        con_lista = False
    return _fragmento(request, _contexto(vista, copias, mensaje_pedir, con_lista=con_lista,
                                        oob_accion=cambia, vr=vr, restaurando=restaurando))


@router.get("/ui/copias/estado", response_class=HTMLResponse)
async def estado_copias(request: Request) -> HTMLResponse:
    return await _fragmento_actual(request)


@router.post("/ui/copias/pedir", response_class=HTMLResponse)
async def pedir_copia(request: Request) -> HTMLResponse:
    """Pide una copia al auxiliar. Si ya hay una en marcha NO envía nada y devuelve el estado actual (FR-24)."""
    global _tarea_copia
    settings = get_settings()
    vista = await asyncio.to_thread(ops_host.resolver_estado, settings)
    if vista.en_marcha and _tarea_copia is None:
        _tarea_copia = tareas.iniciar_copia()
    elif not vista.en_marcha and _tarea_copia is not None:
        if vista.estado in (EstadoCopia.HECHA, EstadoCopia.DIARIO):
            tareas.terminar(_tarea_copia.id, resumen="Copia terminada")
        else:
            tareas.error(_tarea_copia.id,
                         tipo_error="copia_" + str(vista.estado))
        _tarea_copia = None
    if vista.estado == EstadoCopia.NO_ACTIVADO:
        return await _fragmento_actual(request, boton_cambia=True)
    if (await asyncio.to_thread(ops_host.resolver_restauracion, settings)).en_marcha:
        # Garantía (AC-21): con otra operación en marcha no se contacta con el auxiliar.
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


@router.get("/ui/copias/restauracion", response_class=HTMLResponse)
async def resumen_restauracion(request: Request) -> HTMLResponse:
    """Resumen estable tras reiniciar (UATP-08 D-5): solo lectura de ops-restaurar.json."""
    settings = get_settings()
    vr = await asyncio.to_thread(ops_host.resolver_restauracion, settings)
    respuesta = templates.TemplateResponse(request, "restauracion_resumen.html", {
        "vr": vr, "fecha_absoluta": ops_host.fecha_absoluta,
        "version_llana": ops_host.version_llana, "miles": ops_host.miles,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.get("/ui/copias/restaurar/{copia}", response_class=HTMLResponse)
async def restaurar_confirmar(copia: str, request: Request) -> HTMLResponse:
    """Pantalla de confirmación de BL-OPS2; solo lectura, sin tocar la BD."""
    if not restauracion.RE_COPIA.fullmatch(copia):
        raise HTTPException(status_code=404)
    settings = get_settings()
    revision = None
    from zascarr.database import async_session_factory
    async with async_session_factory() as db:
        revision = await restauracion.revision_actual(db)
    copias = restauracion.ofrecer(ops_host.leer_copias(settings), revision,
                                  settings.auth_mode,
                                  permitir=not ops_host.resolver_restauracion(settings).en_marcha)
    elegida = next((c for c in copias if c["id"] == copia), None)
    if elegida is None:
        raise HTTPException(status_code=404)
    restaurando = ops_host.resolver_restauracion(settings).en_marcha
    respuesta = templates.TemplateResponse(request, "_restaurar_confirmar.html", {
        "copia": elegida, "error": None,
        "version_llana": ops_host.version_llana,
        "fecha_absoluta": ops_host.fecha_absoluta,
        "activa": settings.auth_mode != "none" and not restaurando,
        "restaurando": restaurando,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@router.post("/ui/copias/restaurar", response_class=HTMLResponse)
async def restaurar_solicitar(
    request: Request, copia: str = Form(default=""),
    contrasena: str = Form(default=""), entiendo: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Manual, sin restricciones de Form: ninguna respuesta repite la contraseña."""
    settings = get_settings()
    codigo, mensaje = await restauracion.solicitar(
        db, settings, copia=copia, contrasena=contrasena, entiendo=entiendo == "si")
    respuesta = templates.TemplateResponse(request, "_restaurar_resultado.html", {
        "codigo": codigo, "mensaje": mensaje,
        "aceptada": codigo is CodigoOps.ACEPTADA,
    })
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta
