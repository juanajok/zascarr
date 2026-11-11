"""MIT-M7-US03 (#132-b): pantalla «Decisiones reutilizables» y acciones de ciclo.

El inventario es de solo lectura (`utils`... servicios); las acciones llaman a los
servicios de cada fuente y nunca tocan series, issues ni archivos. Confirmación
explícita e independiente para activar/reactivar/retirar alias.
"""
from __future__ import annotations

from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services import alias_decisiones as alias_svc
from zascarr.services import correspondencias_contexto as corr_svc
from zascarr.services import declaraciones_carpeta as decl_svc
from zascarr.services.decisiones_reutilizables import (
    ESTADO_ES,
    ORIGEN_ES,
    TIPO_ES,
    TIPOS,
    Decision,
    listar_decisiones,
)
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/pendientes/carpetas", tags=["ui"])
templates = crear_templates()

URL_LISTA = "/ui/pendientes/carpetas/decisiones"
ACCION_ES = {
    "activar": "Activar", "desactivar": "Desactivar", "reactivar": "Reactivar",
    "retirar": "Retirar", "cambiar": "Cambiar",
}
_DECL_ACCIONES = {
    "desactivar": decl_svc.desactivar, "reactivar": decl_svc.reactivar,
    "retirar": decl_svc.retirar,
}
_CORR_ACCIONES = {
    "desactivar": corr_svc.desactivar, "reactivar": corr_svc.activar,
    "retirar": corr_svc.retirar,
}


def _respuesta(request: Request, plantilla: str, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _redir(destino: str) -> RedirectResponse:
    resp = RedirectResponse(destino, status_code=303)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _con_aviso(codigo: str) -> str:
    return f"{URL_LISTA}?aviso={quote(codigo)}"


def _con_error(mensaje: str) -> str:
    return f"{URL_LISTA}?error={quote(mensaje)}"


async def _buscar(db: AsyncSession, tipo: str, ident: UUID) -> Decision | None:
    for fila in await listar_decisiones(db, incluir_historial=True):
        if fila.tipo == tipo and str(fila.id) == str(ident):
            return fila
    return None


@router.get("/decisiones", response_class=HTMLResponse)
async def decisiones(request: Request, tipo: str = Query(default=""),
                     estado: str = Query(default=""), origen: str = Query(default=""),
                     carpeta: str = Query(default=""), historial: str = Query(default="0"),
                     aviso: str = Query(default=""), error: str = Query(default=""),
                     db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        filas = await listar_decisiones(
            db, tipo=tipo, estado=estado, origen=origen, carpeta=carpeta,
            incluir_historial=historial == "1")
    except Exception:  # noqa: BLE001 — la pantalla avisa, no vuelca el error interno
        filas = []
        error = error or "No se han podido leer las decisiones. Vuelve a intentarlo."
    return _respuesta(request, "decisiones_reutilizables.html", {
        "filas": filas, "total": len(filas),
        "filtros": {"tipo": tipo, "estado": estado, "origen": origen,
                    "carpeta": carpeta, "historial": historial == "1"},
        "tipos": [(t, TIPO_ES[t]) for t in TIPOS],
        "estados": list(ESTADO_ES.items()),
        "origenes": list(ORIGEN_ES.items()),
        "aviso": aviso, "error": error,
        "url_lista": URL_LISTA,
    })


def _titulo(accion: str, decision: Decision) -> str:
    if accion == "activar":
        return "Activar alias"
    if accion == "reactivar":
        return "Reactivar alias"
    if accion == "retirar":
        return "Retirar decisión"
    return "Confirmar cambio"


@router.get("/decisiones/confirmar/{tipo}/{ident}/{accion}", response_class=HTMLResponse)
async def confirmar(request: Request, tipo: str, ident: UUID, accion: str,
                    db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    decision = await _buscar(db, tipo, ident)
    if decision is None:
        return _redir(_con_error("Esa decisión ya no existe."))
    if accion not in ("activar", "reactivar", "retirar"):
        return _redir(_con_error("Esa acción no existe."))
    return _respuesta(request, "confirmar_decision.html", {
        "decision": decision, "accion": accion,
        "titulo": _titulo(accion, decision),
        "boton": {"activar": "Sí, activar este alias",
                  "reactivar": "Sí, reactivar este alias",
                  "retirar": "Sí, retirar esta decisión"}[accion],
        "url_lista": URL_LISTA,
        "url_accion": f"{URL_LISTA}/accion/{tipo}/{ident}/{accion}",
    })


@router.post("/decisiones/accion/{tipo}/{ident}/{accion}", response_class=HTMLResponse)
async def accion(request: Request, tipo: str, ident: UUID, accion: str,
                 confirmado: str = Form(default=""),
                 db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    decision = await _buscar(db, tipo, ident)
    if decision is None:
        return _redir(_con_error("Esa decisión ya no existe."))
    if decision.es_importada and tipo in ("declaracion", "correspondencia"):
        return _redir(_con_error("Una decisión importada se muestra, no se gestiona aquí."))
    requiere_confirmacion = accion in ("activar", "reactivar", "retirar")
    if requiere_confirmacion and confirmado != "1":
        return _redir(_con_error("Esta acción necesita una confirmación explícita."))
    try:
        if tipo == "declaracion":
            if accion not in _DECL_ACCIONES:
                return _redir(_con_error("Esa acción no existe."))
            await _DECL_ACCIONES[accion](db, ident)
        elif tipo == "correspondencia":
            if accion not in _CORR_ACCIONES:
                return _redir(_con_error("Esa acción no existe."))
            await _CORR_ACCIONES[accion](db, ident)
        elif tipo == "alias_aprendido":
            if accion == "activar":
                await alias_svc.activar_local(db, ident, confirmado=True)
            elif accion == "desactivar":
                await alias_svc.desactivar_local(db, ident)
            elif accion == "reactivar":
                await alias_svc.reactivar_local(db, ident, confirmado=True)
            elif accion == "retirar":
                await alias_svc.retirar_local(db, ident)
            else:
                return _redir(_con_error("Esa acción no existe."))
        elif tipo == "alias_importado":
            if accion == "activar":
                await alias_svc.activar_importado(db, ident, confirmado=True)
            elif accion == "desactivar":
                await alias_svc.desactivar_importado(db, ident)
            elif accion == "reactivar":
                await alias_svc.reactivar_importado(db, ident, confirmado=True)
            elif accion == "retirar":
                await alias_svc.retirar_importado(db, ident)
            else:
                return _redir(_con_error("Esa acción no existe."))
        else:
            return _redir(_con_error("Ese tipo de decisión no existe."))
    except (decl_svc.DeclaracionRetiradaError, corr_svc.TipoInvalidoError,
            alias_svc.TransicionInvalidaError, alias_svc.AliasNoEncontradoError) as exc:
        return _redir(_con_error(str(exc)))
    except Exception:  # noqa: BLE001
        return _redir(_con_error("No se ha podido completar la acción. Vuelve a intentarlo."))
    aviso = {"activar": "activada", "desactivar": "desactivada",
             "reactivar": "reactivada", "retirar": "retirada"}[accion]
    return _redir(_con_aviso(aviso))
