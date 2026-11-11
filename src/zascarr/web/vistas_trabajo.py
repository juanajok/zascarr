"""BL-R7 (#236): vistas de trabajo predefinidas (solo lectura).

Cada vista es una consulta viva, no una lista guardada ni una colección: el archivo
entra o sale según su estado. Abrir una vista no escribe nada.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services.vistas_trabajo import (
    CLAVES,
    POR_PAGINA,
    PaginaVista,
    ResumenVista,
    listar_vista,
    resumen_de_vistas,
)
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/vistas", tags=["ui"])
templates = crear_templates()

URL_VISTAS = "/ui/vistas"
EFECTOS = ("Estas vistas son consultas vivas: no guardan listas ni cambian nada. "
           "No mueven, renombran ni borran archivos.")


def _respuesta(request: Request, plantilla: str, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("", response_class=HTMLResponse)
async def vistas(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        resumen: list[ResumenVista] = await resumen_de_vistas(db)
    except Exception:  # noqa: BLE001 — la pantalla avisa; no inventa recuentos parciales
        return _respuesta(request, "vistas_trabajo.html", {
            "vistas": [], "error": True, "efectos": EFECTOS, "url_vistas": URL_VISTAS,
        })
    return _respuesta(request, "vistas_trabajo.html", {
        "vistas": resumen, "error": False, "efectos": EFECTOS, "url_vistas": URL_VISTAS,
    })


@router.get("/{clave}", response_class=HTMLResponse)
async def vista(clave: str, request: Request, pagina: int = Query(default=1, ge=1),
                db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    if clave == "no-disponibles":
        return RedirectResponse("/ui/no-disponibles", status_code=303)
    if clave not in CLAVES:
        raise HTTPException(status_code=404, detail="Vista no encontrada")
    try:
        pv: PaginaVista | None = await listar_vista(db, clave, pagina)
    except Exception:  # noqa: BLE001
        return _respuesta(request, "vista_trabajo.html", {
            "pagina": None, "error": True, "efectos": EFECTOS, "url_vistas": URL_VISTAS,
            "por_pagina": POR_PAGINA,
        })
    if pv is None:
        raise HTTPException(status_code=404, detail="Vista no encontrada")
    return _respuesta(request, "vista_trabajo.html", {
        "pagina": pv, "error": False, "efectos": EFECTOS, "url_vistas": URL_VISTAS,
        "por_pagina": POR_PAGINA,
    })
