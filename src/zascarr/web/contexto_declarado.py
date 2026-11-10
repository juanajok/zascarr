# ruff: noqa: E501
"""MIT-M7 130-b: declarar el significado de una carpeta desde la revisión.

Formularios POST explícitos y PRG; sin JS nuevo. La ruta llega en `clave`,
se valida en servidor y es la identidad: no hay campo libre.
"""
from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services import declaraciones_carpeta as svc
from zascarr.services.declaraciones_carpeta import DeclaracionVista
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/pendientes/carpetas", tags=["ui"])
templates = crear_templates()

MSG_EFECTOS = ("No crea series, no mueve archivos, no vincula nada; solo orienta próximas "
               "interpretaciones. No cambia lo ya decidido.")
MSG_RUTA_INVALIDA = ("La ruta de esta carpeta no es válida. Vuelve a «Pendientes por carpeta» "
                     "y elige la carpeta desde ahí.")
MSG_RAIZ = ("No se puede declarar la raíz de la biblioteca: alcanzaría todas las carpetas. "
            "Elige una carpeta dentro de ella.")
MSG_NO_ENCONTRADA = "Esa declaración ya no existe. Vuelve a «Contexto declarado»."
MSG_RUTA_FUERA = "La carpeta tiene que estar dentro de tu biblioteca y ser una ruta relativa."
MSG_RUTA_LARGA = "La ruta es demasiado larga."


def _volver() -> str:
    return "/ui/pendientes/carpetas"


def _url_declarar(clave: str, *, tipo: str = "", incluir: bool = False) -> str:
    url = f"/ui/pendientes/carpetas/declarar?clave={quote(clave, safe='')}"
    if tipo:
        url += f"&tipo={quote(tipo)}"
    if incluir:
        url += "&incluir=1"
    return url


def _respuesta(request: Request, plantilla: str, contexto: dict, *,
               status_code: int = 200) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto, status_code=status_code)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _redir(url: str) -> RedirectResponse:
    respuesta = RedirectResponse(url, status_code=303)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _error(request: Request, mensaje: str) -> HTMLResponse:
    return _respuesta(request, "declaracion_error.html",
                      {"mensaje": mensaje, "volver": _volver()})


def _actual(declaraciones: list[DeclaracionVista], ruta: str) -> list[DeclaracionVista]:
    return [d for d in declaraciones if d.contexto_raiz == ruta]


def _local(actuales: list[DeclaracionVista]) -> DeclaracionVista | None:
    return next((d for d in actuales if d.origen.value == "local"), None)


def _local_viva(actuales: list[DeclaracionVista]) -> DeclaracionVista | None:
    """Una local retirada no impide crear una identidad nueva (P10)."""
    return next((d for d in actuales
                 if d.origen.value == "local" and d.estado.value != "retirada"), None)


def _resumen(actuales: list[DeclaracionVista]) -> dict:
    local = _local(actuales)
    return {
        "actual": local or (actuales[0] if actuales else None),
        "actual_local": local,
        "alternativas": [d for d in actuales if local is None or d.id != local.id],
        "hay_importacion": any(d.origen.value == "importacion" for d in actuales),
        "conflicto": bool(local and any(d.origen.value == "importacion" for d in actuales)),
    }


@router.get("/contexto", response_class=HTMLResponse)
async def contexto(request: Request, aviso: str = Query(default=""),
                   db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        todas = await svc.listar(db)
    except Exception:  # noqa: BLE001 — la página avisa, no filtra un error interno
        return _error(request, "No se ha podido leer el contexto declarado. Vuelve a intentarlo.")
    secciones = [(estado, [d for d in todas if d.estado.value == estado])
                 for estado in ("activa", "desactivada", "retirada")]
    por_ruta: dict[str, list[DeclaracionVista]] = {}
    for d in todas:
        por_ruta.setdefault(d.contexto_raiz, []).append(d)
    conflictos = {
        ruta: [x for x in filas if x.origen.value == "importacion"]
        for ruta, filas in por_ruta.items()
        if any(x.origen.value == "local" and x.estado.value == "activa" for x in filas)
        and any(x.origen.value == "importacion" for x in filas)
    }
    return _respuesta(request, "contexto_declarado.html", {
        "secciones": secciones, "todas": todas, "volver": _volver(),
        "aviso": aviso, "conflictos": conflictos,
        "url_contexto": "/ui/pendientes/carpetas/contexto"})


@router.get("/declarar", response_class=HTMLResponse)
async def declarar_form(request: Request, clave: str = "", tipo: str = Query(default=""),
                        incluir: str = Query(default="0"), estado: str = Query(default=""),
                        error: str = Query(default=""),
                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    if not clave.strip():
        return _error(request, "No sabemos qué carpeta quieres declarar. Vuelve a «Pendientes por carpeta» y elige una.")
    try:
        raiz = str(get_settings().library_path)
        if clave.strip().replace("\\", "/").rstrip("/") == raiz.replace("\\", "/").rstrip("/"):
            return _error(request, MSG_RAIZ)
        ruta = svc.normalizar_ruta(clave, raiz_biblioteca=raiz)
    except svc.RutaInvalidaError as exc:
        detalle = str(exc)
        if "raíz" in detalle:
            return _error(request, MSG_RAIZ)
        if "relativa" in detalle:
            return _error(request, MSG_RUTA_FUERA)
        if "larga" in detalle:
            return _error(request, MSG_RUTA_LARGA)
        return _error(request, MSG_RUTA_INVALIDA)
    try:
        actuales = _actual(await svc.listar(db), ruta)
    except Exception:  # noqa: BLE001
        return _error(request, "No se ha podido leer el contexto declarado. Vuelve a intentarlo.")
    return _respuesta(request, "declarar_carpeta.html", {
        "ruta": ruta, "resumen": _resumen(actuales), "clave": ruta,
        "tipo": tipo, "incluir": incluir == "1", "error": error,
        "mensaje_efectos": MSG_EFECTOS, "volver": _volver(),
    })


@router.post("/declarar", response_class=HTMLResponse)
async def declarar_post(request: Request,
                        clave: str = Form(...), tipo: str = Form(default=""),
                        incluir: str = Form(default="0"), confirmado: str = Form(default="0"),
                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        raiz = str(get_settings().library_path)
        if clave.strip().replace("\\", "/").rstrip("/") == raiz.replace("\\", "/").rstrip("/"):
            return _error(request, MSG_RAIZ)
        ruta = svc.normalizar_ruta(clave, raiz_biblioteca=raiz)
    except svc.RutaInvalidaError as exc:
        detalle = str(exc)
        if "raíz" in detalle:
            return _error(request, MSG_RAIZ)
        if "relativa" in detalle:
            return _error(request, MSG_RUTA_FUERA)
        if "larga" in detalle:
            return _error(request, MSG_RUTA_LARGA)
        return _error(request, MSG_RUTA_INVALIDA)
    incluir_bool = incluir == "1"
    if not tipo:
        return _respuesta(request, "declarar_carpeta.html", {
            "ruta": ruta, "resumen": _resumen([]), "clave": ruta, "tipo": "",
            "incluir": incluir_bool,
            "error": "Elige qué significa la carpeta antes de guardar.",
            "mensaje_efectos": MSG_EFECTOS, "volver": _volver()})
    if incluir_bool and confirmado != "1":
        return _respuesta(request, "confirmar_alcance.html", {
            "accion": "/ui/pendientes/carpetas/declarar", "volver_url": _url_declarar(ruta, tipo=tipo, incluir=incluir_bool),
            "clave": ruta, "tipo": tipo, "tipo_texto": _tipo_texto(tipo),
            "incluir": "1", "es_cambio": False, "version_actual": None,
            "volver": _volver()})
    try:
        actuales = _actual(await svc.listar(db), ruta)
        if _local_viva(actuales) is not None:
            return _error(request, "Esta carpeta ya tiene una declaración. Ábrela para cambiarla o retirarla.")
        await svc.declarar(db, ruta, tipo_de_significado=tipo, incluir_descendientes=incluir_bool)
    except svc.TipoInvalidoError as exc:
        return _respuesta(request, "declarar_carpeta.html", {
            "ruta": ruta, "resumen": _resumen([]), "clave": ruta, "tipo": tipo,
            "incluir": incluir_bool, "error": str(exc),
            "mensaje_efectos": MSG_EFECTOS, "volver": _volver()})
    except svc.DeclaracionDuplicadaError as exc:
        return _error(request, str(exc))
    except svc.DeclaracionError as exc:
        return _respuesta(request, "declarar_carpeta.html", {
            "ruta": ruta, "resumen": _resumen([]), "clave": ruta, "tipo": tipo,
            "incluir": incluir_bool,
            "error": f"No se ha podido guardar la declaración. No se ha cambiado nada. Vuelve a intentarlo. ({exc})",
            "mensaje_efectos": MSG_EFECTOS, "volver": _volver()}, status_code=200)
    return _redir("/ui/pendientes/carpetas/contexto?aviso=guardada")


@router.get("/cambiar/{declaracion_id}", response_class=HTMLResponse)
async def cambiar_form(request: Request, declaracion_id: UUID,
                       tipo: str = Query(default=""), incluir: str = Query(default="0"),
                       error: str = Query(default=""),
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual_por_id(db, declaracion_id)
    if actual is None:
        return _error(request, MSG_NO_ENCONTRADA)
    if actual.estado.value == "retirada":
        return _error(request, "Una declaración retirada no se puede cambiar.")
    return _respuesta(request, "cambiar_declaracion.html", {
        "d": actual, "volver": _volver(), "mensaje_efectos": MSG_EFECTOS,
        "tipo_actual": tipo or actual.tipo_de_significado.value,
        "incluir_actual": (incluir == "1") if incluir else actual.incluir_descendientes,
        "error": error})


@router.post("/cambiar/{declaracion_id}", response_class=HTMLResponse)
async def cambiar_post(request: Request, declaracion_id: UUID,
                       tipo: str = Form(default=""), incluir: str = Form(default="0"),
                       confirmado: str = Form(default="0"),
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual_por_id(db, declaracion_id)
    if actual is None:
        return _error(request, MSG_NO_ENCONTRADA)
    if actual.estado.value == "retirada":
        return _error(request, "Una declaración retirada no se puede cambiar.")
    incluir_bool = incluir == "1"
    if tipo not in ("autor", "publicacion"):
        return _respuesta(request, "cambiar_declaracion.html", {
            "d": actual, "volver": _volver(), "mensaje_efectos": MSG_EFECTOS,
            "tipo_actual": tipo, "incluir_actual": incluir_bool,
            "error": "Elige qué significa la carpeta antes de guardar."})
    if incluir_bool and not actual.incluir_descendientes and confirmado != "1":
        return _respuesta(request, "confirmar_alcance.html", {
            "accion": f"/ui/pendientes/carpetas/cambiar/{declaracion_id}",
            "volver_url": (f"/ui/pendientes/carpetas/cambiar/{declaracion_id}"
                           f"?tipo={tipo}&incluir={'1' if incluir_bool else '0'}"),
            "clave": actual.contexto_raiz, "tipo": tipo, "tipo_texto": _tipo_texto(tipo),
            "incluir": "1", "es_cambio": True, "version_actual": actual.version,
            "volver": _volver()})
    if tipo == actual.tipo_de_significado.value and incluir_bool == actual.incluir_descendientes:
        return _respuesta(request, "cambiar_declaracion.html", {
            "d": actual, "volver": _volver(), "mensaje_efectos": MSG_EFECTOS,
            "tipo_actual": tipo, "incluir_actual": incluir_bool,
            "error": "No has cambiado nada."})
    await svc.cambiar(db, declaracion_id, tipo_de_significado=tipo,
                      incluir_descendientes=incluir_bool)
    return _redir("/ui/pendientes/carpetas/contexto?aviso=actualizada")


@router.post("/desactivar/{declaracion_id}", response_class=HTMLResponse)
async def desactivar(request: Request, declaracion_id: UUID,
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual_por_id(db, declaracion_id)
    if actual is None:
        return _error(request, MSG_NO_ENCONTRADA)
    if actual.estado.value == "retirada":
        return _error(request, "Una declaración retirada no se puede desactivar.")
    await svc.desactivar(db, declaracion_id)
    return _redir("/ui/pendientes/carpetas/contexto?aviso=desactivada")


@router.post("/reactivar/{declaracion_id}", response_class=HTMLResponse)
async def reactivar(request: Request, declaracion_id: UUID,
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual_por_id(db, declaracion_id)
    if actual is None:
        return _error(request, MSG_NO_ENCONTRADA)
    if actual.estado.value == "retirada":
        return _error(request, "Una declaración retirada no se puede reactivar. Crea una declaración nueva desde la carpeta.")
    await svc.reactivar(db, declaracion_id)
    return _redir("/ui/pendientes/carpetas/contexto?aviso=reactivada")


@router.get("/retirar/{declaracion_id}", response_class=HTMLResponse)
async def retirar_form(request: Request, declaracion_id: UUID,
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual_por_id(db, declaracion_id)
    if actual is None:
        return _error(request, MSG_NO_ENCONTRADA)
    if actual.estado.value == "retirada":
        return _error(request, "Una declaración retirada no se puede retirar otra vez.")
    return _respuesta(request, "retirar_declaracion.html", {"d": actual, "volver": _volver()})


@router.post("/retirar/{declaracion_id}", response_class=HTMLResponse)
async def retirar_post(request: Request, declaracion_id: UUID,
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    actual = await _actual_por_id(db, declaracion_id)
    if actual is None:
        return _error(request, MSG_NO_ENCONTRADA)
    if actual.estado.value == "retirada":
        return _error(request, "Una declaración retirada no se puede retirar otra vez.")
    await svc.retirar(db, declaracion_id)
    return _redir("/ui/pendientes/carpetas/contexto?aviso=retirada")


async def _actual_por_id(db: AsyncSession, identificador: UUID) -> DeclaracionVista | None:
    """Acepta el id estable y, por compatibilidad, el id de una fila-versión."""
    try:
        filas = await svc.historial(db, identificador)
        if not filas:
            fila = await db.get(
                __import__("zascarr.models", fromlist=["DeclaracionCarpeta"]).DeclaracionCarpeta,
                identificador)
            if fila is not None:
                filas = await svc.historial(db, fila.declaracion_id)
    except svc.DeclaracionError:
        return None
    return next((f for f in filas if f.vigente_hasta is None), None)


def _tipo_texto(tipo: str) -> str:
    return "Por autor" if tipo == "autor" else "Por publicación"
