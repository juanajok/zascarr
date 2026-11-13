"""#155/BL-D6: UI de colecciones y su política de auto-búsqueda."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
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
from zascarr.services.exportacion_kavita import (
    ExportacionError,
    exportar_coleccion,
    historial_exportaciones,
)
from zascarr.services.portada_coleccion import (
    candidatas_portada,
    elegir_portada,
    obtener_portada,
)
from zascarr.utils.cover import cached_image_response
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/colecciones", tags=["ui"])
templates = crear_templates()

POLITICAS = {
    CollectionAutoSearch.HEREDAR: "Como cada serie",
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
        "candidatas_portada": await candidatas_portada(db, coleccion_id),
        "exportaciones": await historial_exportaciones(db, coleccion_id),
        "errores": {}, "aviso": {
            "guardada": "Colección guardada.",
            "asignada": "Serie añadida a la colección.",
            "quitada": "Serie quitada de la colección; sigue en tu biblioteca.",
            "portada": "Portada actualizada.",
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


@router.get("/{coleccion_id}/portada")
@router.get("/{coleccion_id}/portada.jpg")
async def portada(coleccion_id: UUID, request: Request,
                  db: AsyncSession = Depends(get_db)) -> Response:
    resultado = await obtener_portada(db, coleccion_id)
    if resultado is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    if not resultado.cacheable:
        return Response(content=resultado.datos, media_type=resultado.content_type,
                        headers={"Cache-Control": "no-store"})
    return cached_image_response(request, resultado.datos, resultado.content_type, resultado.etag)


@router.post("/{coleccion_id}/portada")
async def cambiar_portada(request: Request, coleccion_id: UUID,
                          series_id: str = Form(""), db: AsyncSession = Depends(get_db)):
    elegida = None
    if series_id.strip():
        try:
            elegida = UUID(series_id)
        except ValueError:
            c = await detalle_coleccion(db, coleccion_id)
            return _respuesta(request, "coleccion_detalle.html", {
                "coleccion": c, "politicas": POLITICAS,
                "series": await series_sin_coleccion(db),
                "candidatas_portada": await candidatas_portada(db, coleccion_id),
                "exportaciones": await historial_exportaciones(db, coleccion_id),
                "errores": {"portada": "La serie elegida no es válida."}, "aviso": ""})
    r = await elegir_portada(db, coleccion_id, elegida)
    if not r.ok:
        c = await detalle_coleccion(db, coleccion_id)
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": c, "politicas": POLITICAS,
            "series": await series_sin_coleccion(db),
            "candidatas_portada": await candidatas_portada(db, coleccion_id),
            "exportaciones": await historial_exportaciones(db, coleccion_id),
            "errores": r.errores, "aviso": ""})
    await db.commit()
    return _redirigir(f"/ui/colecciones/{coleccion_id}?guardado=portada")


@router.post("/{coleccion_id}/exportar")
async def exportar(request: Request, coleccion_id: UUID, patch_comicinfo: str = Form("0"),
                   copiar: str = Form("0"), confirmo: str = Form("0"),
                   db: AsyncSession = Depends(get_db)):
    c = await detalle_coleccion(db, coleccion_id)
    if c is None:
        return _redirigir("/ui/colecciones")
    if confirmo != "1":
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": c, "politicas": POLITICAS,
            "series": await series_sin_coleccion(db),
            "exportaciones": await historial_exportaciones(db, coleccion_id),
            "errores": {"general": "Marca la confirmación antes de exportar."}, "aviso": "",
        })
    try:
        resumen = await exportar_coleccion(
            db, coleccion_id, patch_comicinfo=patch_comicinfo == "1",
            copiar=copiar == "1")
        await db.commit()
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": c, "politicas": POLITICAS,
            "series": await series_sin_coleccion(db),
            "exportaciones": await historial_exportaciones(db, coleccion_id),
            "errores": {}, "exportacion": resumen, "aviso": "",
        })
    except ExportacionError as exc:
        error = str(exc)
    return _respuesta(request, "coleccion_detalle.html", {
        "coleccion": c, "politicas": POLITICAS,
        "series": await series_sin_coleccion(db),
        "exportaciones": await historial_exportaciones(db, coleccion_id),
        "errores": {"general": error}, "aviso": "",
    })


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
