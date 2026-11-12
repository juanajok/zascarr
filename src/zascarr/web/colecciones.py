"""#155/BL-D6: UI de colecciones y su política de auto-búsqueda."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import CollectionAutoSearch
from zascarr.services.colecciones import (
    asignar_serie,
    borrar_coleccion,
    crear_coleccion,
    detalle_coleccion,
    editar_coleccion,
    listar_colecciones,
    quitar_serie,
    series_sin_coleccion,
)
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/colecciones", tags=["ui"])
templates = crear_templates()

POLITICAS = {
    CollectionAutoSearch.HEREDAR: "Como cada serie (heredar)",
    CollectionAutoSearch.INCLUIR: "Buscar faltantes de todas",
    CollectionAutoSearch.EXCLUIR: "No buscar automáticamente",
}


def _respuesta(request: Request, plantilla: str, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _redirigir(destino: str) -> RedirectResponse:
    return RedirectResponse(destino, status_code=303)


@router.get("", response_class=HTMLResponse)
async def colecciones(request: Request, guardado: str = "", db: AsyncSession = Depends(get_db)):
    return _respuesta(request, "colecciones.html", {
        "colecciones": await listar_colecciones(db),
        "politicas": POLITICAS,
        "aviso": {
            "creada": "Colección creada.",
            "guardada": "Colección guardada.",
            "borrada": "Colección eliminada. Sus series siguen en tu biblioteca, sin colección.",
            "asignada": "Serie añadida a la colección.",
            "quitada": "Serie quitada de la colección; sigue en tu biblioteca.",
        }.get(guardado, ""),
    })


@router.post("/nueva")
async def nueva(request: Request, name: str = Form(""), description: str = Form(""),
                auto_search: str = Form("heredar"), db: AsyncSession = Depends(get_db)):
    r = await crear_coleccion(db, name=name, description=description, auto_search=auto_search)
    if not r.ok:
        return _respuesta(request, "colecciones.html", {
            "colecciones": await listar_colecciones(db), "politicas": POLITICAS,
            "valores": {"name": name, "description": description, "auto_search": auto_search},
            "errores": r.errores, "aviso": "",
        })
    await db.commit()
    return _redirigir("/ui/colecciones?guardado=creada")


@router.get("/{coleccion_id}", response_class=HTMLResponse)
async def detalle(request: Request, coleccion_id: UUID, guardado: str = "",
                  db: AsyncSession = Depends(get_db)):
    c = await detalle_coleccion(db, coleccion_id)
    if c is None:
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": None, "politicas": POLITICAS, "series": [],
            "errores": {"general": "La colección ya no existe."}, "aviso": ""})
    return _respuesta(request, "coleccion_detalle.html", {
        "coleccion": c, "politicas": POLITICAS,
        "series": await series_sin_coleccion(db),
        "errores": {}, "aviso": {
            "guardada": "Colección guardada.",
            "asignada": "Serie añadida a la colección.",
            "quitada": "Serie quitada de la colección; sigue en tu biblioteca.",
        }.get(guardado, ""),
    })


@router.post("/{coleccion_id}/editar")
async def editar(request: Request, coleccion_id: UUID, name: str = Form(""),
                 description: str = Form(""), auto_search: str = Form("heredar"),
                 db: AsyncSession = Depends(get_db)):
    r = await editar_coleccion(db, coleccion_id, name=name, description=description,
                               auto_search=auto_search)
    if not r.ok:
        c = await detalle_coleccion(db, coleccion_id)
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": c, "politicas": POLITICAS,
            "series": await series_sin_coleccion(db),
            "valores": {"name": name, "description": description, "auto_search": auto_search},
            "errores": r.errores, "aviso": "",
        })
    await db.commit()
    return _redirigir(f"/ui/colecciones/{coleccion_id}?guardado=guardada")


@router.post("/{coleccion_id}/borrar")
async def borrar(coleccion_id: UUID, db: AsyncSession = Depends(get_db)):
    await borrar_coleccion(db, coleccion_id)
    await db.commit()
    return _redirigir("/ui/colecciones?guardado=borrada")


@router.post("/{coleccion_id}/series")
async def asignar(request: Request, coleccion_id: UUID, serie_id: UUID = Form(...),
                  db: AsyncSession = Depends(get_db)):
    r = await asignar_serie(db, coleccion_id, serie_id)
    if not r.ok:
        c = await detalle_coleccion(db, coleccion_id)
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": c, "politicas": POLITICAS,
            "series": await series_sin_coleccion(db), "errores": r.errores, "aviso": ""})
    await db.commit()
    return _redirigir(f"/ui/colecciones/{coleccion_id}?guardado=asignada")


@router.post("/{coleccion_id}/series/{serie_id}/quitar")
async def quitar(coleccion_id: UUID, serie_id: UUID, db: AsyncSession = Depends(get_db)):
    await quitar_serie(db, coleccion_id, serie_id)
    await db.commit()
    return _redirigir(f"/ui/colecciones/{coleccion_id}?guardado=quitada")
