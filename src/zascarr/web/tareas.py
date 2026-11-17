"""#991 C1: API y fragmento HTMX del indicador global de tareas."""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from zascarr.services import tareas
from zascarr.web.routes import crear_templates

templates = crear_templates()
api_router = APIRouter(prefix="/api", tags=["tareas"])
ui_router = APIRouter()


@api_router.get("/tareas")
async def api_tareas() -> JSONResponse:
    datos = tareas.snapshot(incluir_recientes=True, consumir_anuncio=False)
    cuerpo = {
        "version": 1,
        "generado": datos["generado"],
        "resumen": datos["resumen"],
        "tareas": [{k: t[k] for k in ("id", "tipo", "titulo", "fase", "hechos",
                                     "total", "pct", "unidad", "estado", "atascada",
                                     "iniciada", "actualizada", "enlace", "detalle",
                                     "run_id", "visto")}
                   for t in datos["tareas"]],
    }
    return JSONResponse(cuerpo, headers={"Cache-Control": "no-store"})


@ui_router.get("/ui/_tareas", response_class=HTMLResponse)
async def fragmento_tareas(request: Request) -> HTMLResponse:
    datos = tareas.snapshot(incluir_recientes=True, consumir_anuncio=True)
    respuesta = templates.TemplateResponse(request, "_tareas.html", {"t": datos})
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


@ui_router.post("/ui/_tareas/visto", response_class=HTMLResponse)
async def marcar_visto_form(request: Request, tid: str = Form("")) -> HTMLResponse:
    """Contrato: POST con `tid`; vacío/«ultimo» marca el error más reciente."""
    if tid and tid != "ultimo":
        tareas.marcar_visto(tid)
    else:
        tareas.marcar_visto_ultimo()
    return await fragmento_tareas(request)


@ui_router.post("/ui/_tareas/visto/{tid}", response_class=HTMLResponse)
async def marcar_visto(request: Request, tid: str) -> HTMLResponse:
    """Contrato definitivo: POST /ui/_tareas/visto/{tid}."""
    if tid == "ultimo":
        tareas.marcar_visto_ultimo()
    else:
        tareas.marcar_visto(tid)
    return await fragmento_tareas(request)


@ui_router.post("/ui/_tareas/ver", response_class=HTMLResponse)
async def ver_tarea(request: Request, tid: str = Form("")) -> HTMLResponse:
    tareas.marcar_visto(tid)
    return await fragmento_tareas(request)
