"""#155/BL-D6: UI de colecciones y su política de auto-búsqueda."""
from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import Collection, CollectionAutoSearch, ComicTradition, Series
from zascarr.services.colecciones import (
    asignar_series,
    borrar_coleccion,
    crear_coleccion,
    detalle_coleccion,
    editar_coleccion,
    listar_colecciones,
    pagina_series_sin_coleccion,
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
from zascarr.web.library import _TRADICION_LABEL
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/colecciones", tags=["ui"])
templates = crear_templates()

TRADICIONES = [(t.value, _TRADICION_LABEL[t]) for t in ComicTradition]


def _seleccion_valida(valores: list[str]) -> list[str]:
    salida: list[str] = []
    for valor in valores:
        try:
            sid = str(UUID(valor))
        except (ValueError, TypeError):
            continue
        if sid not in salida:
            salida.append(sid)
    return salida


def _filtros(q: str, tradicion: str) -> tuple[str, str]:
    texto = (q or "").strip()[:120]
    trad = tradicion if tradicion in {t.value for t in ComicTradition} else ""
    return texto, trad


def _url_ficha(cid: UUID, q: str, tradicion: str, seleccion: list[str],
               pagina: int = 1) -> str:
    params: list[tuple[str, str]] = [("q", q), ("tradicion", tradicion),
                                     ("pagina", str(pagina))]
    params += [("serie_ids", sid) for sid in seleccion]
    return f"/ui/colecciones/{cid}?{urlencode(params)}"


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
            "asignadas": "Series añadidas a la colección.",
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
                  navegar: str = "",
                  q: str = Query(""), tradicion: str = Query(""),
                  serie_ids: list[str] = Query([]),
                  pagina: int = Query(1, ge=1), limpiar: str = Query(""),
                  db: AsyncSession = Depends(get_db)):
    c = await detalle_coleccion(db, coleccion_id)
    if c is None:
        return _respuesta(request, "coleccion_detalle.html", {
            "coleccion": None, "politicas": POLITICAS, "series": [],
            "errores": {"general": "La colección ya no existe."}, "aviso": ""})
    q, tradicion = _filtros(q, tradicion)
    if limpiar == "1":
        q, tradicion = "", ""
    seleccion = _seleccion_valida(serie_ids)
    pagina_datos = await pagina_series_sin_coleccion(
        db, q=q, tradicion=tradicion, pagina=pagina)
    visibles = {s.id for s in pagina_datos.series}
    seleccion_oculta = [sid for sid in seleccion if sid not in visibles]
    return _respuesta(request, "coleccion_detalle.html", {
        "coleccion": c, "politicas": POLITICAS,
        "series": pagina_datos.series, "pagina": pagina_datos,
        "q": q, "tradicion": tradicion, "tradiciones": TRADICIONES,
        "seleccion": seleccion, "seleccion_oculta": seleccion_oculta,
        "foco_filtros": bool(q or tradicion or limpiar == "1" or pagina > 1
                            or navegar == "1"),
        "url_anterior": _url_ficha(coleccion_id, q, tradicion, seleccion,
                                   max(1, pagina_datos.pagina - 1)),
        "url_siguiente": _url_ficha(coleccion_id, q, tradicion, seleccion,
                                    min(pagina_datos.paginas, pagina_datos.pagina + 1)),
        "url_limpiar": _url_ficha(coleccion_id, "", "", seleccion, 1) + "&limpiar=1",
        "candidatas_portada": await candidatas_portada(db, coleccion_id),
        "exportaciones": await historial_exportaciones(db, coleccion_id),
        "errores": {}, "aviso": {
            "guardada": "Colección guardada.",
            "asignada": "Serie añadida a la colección.",
            "asignadas": "Series añadidas a la colección.",
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


@router.get("/{coleccion_id}/previa/{serie_id}", response_class=HTMLResponse)
async def previa_serie(request: Request, coleccion_id: UUID, serie_id: UUID,
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Fragmento HTMX con la portada local de una serie; no toca disco ni red."""
    coleccion = await db.get(Collection, coleccion_id)
    serie = await db.get(Series, serie_id) if coleccion is not None else None
    if coleccion is None or serie is None:
        return HTMLResponse("", status_code=404, headers={"Cache-Control": "no-store"})
    resp = templates.TemplateResponse(
        request, "_previa_serie.html", {"serie": serie})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/{coleccion_id}/portada")
async def cambiar_portada(request: Request, coleccion_id: UUID,
                          series_id: str = Form(""), db: AsyncSession = Depends(get_db)):
    elegida = None
    if series_id.strip():
        try:
            elegida = UUID(series_id)
        except ValueError:
            c = await detalle_coleccion(db, coleccion_id)
            pagina_datos = await pagina_series_sin_coleccion(db)
            return _respuesta(request, "coleccion_detalle.html", {
                "coleccion": c, "politicas": POLITICAS,
                "series": pagina_datos.series, "pagina": pagina_datos,
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
async def asignar(request: Request, coleccion_id: UUID, navegar: str = "",
                  serie_ids: list[str] = Form([]), serie_id: str = Form(""),
                  q: str = Form(""), tradicion: str = Form(""),
                  pagina: int = Form(1), db: AsyncSession = Depends(get_db)):
    crudos = [s for s in serie_ids if s.strip()]
    if serie_id.strip():
        crudos.append(serie_id)
    elegidas: list[UUID] = []
    invalidas = False
    for crudo in crudos:
        try:
            elegidas.append(UUID(crudo))
        except ValueError:
            invalidas = True
            break
    if invalidas:
        r_errores = {"serie": "Hay una serie elegida que no es válida. No se ha añadido ninguna."}
    else:
        r = await asignar_series(db, coleccion_id, elegidas)
        if r.ok:
            await db.commit()
            q, tradicion = _filtros(q, tradicion)
            consulta = {"guardado": "asignadas"}
            if q:
                consulta["q"] = q
            if tradicion:
                consulta["tradicion"] = tradicion
            return _redirigir(f"/ui/colecciones/{coleccion_id}?{urlencode(consulta)}")
        r_errores = r.errores
    c = await detalle_coleccion(db, coleccion_id)
    q, tradicion = _filtros(q, tradicion)
    seleccion = _seleccion_valida(crudos)
    pagina_datos = await pagina_series_sin_coleccion(
        db, q=q, tradicion=tradicion, pagina=pagina)
    visibles = {s.id for s in pagina_datos.series}
    return _respuesta(request, "coleccion_detalle.html", {
        "coleccion": c, "politicas": POLITICAS,
        "series": pagina_datos.series, "pagina": pagina_datos,
        "q": q, "tradicion": tradicion, "tradiciones": TRADICIONES,
        "seleccion": seleccion,
        "foco_filtros": bool(q or tradicion or pagina > 1 or navegar == "1"),
        "seleccion_oculta": [sid for sid in seleccion if sid not in visibles],
        "url_anterior": _url_ficha(coleccion_id, q, tradicion, seleccion,
                                   max(1, pagina_datos.pagina - 1)),
        "url_siguiente": _url_ficha(coleccion_id, q, tradicion, seleccion,
                                    min(pagina_datos.paginas, pagina_datos.pagina + 1)),
        "url_limpiar": _url_ficha(coleccion_id, "", "", seleccion, 1) + "&limpiar=1",
        "candidatas_portada": await candidatas_portada(db, coleccion_id),
        "exportaciones": await historial_exportaciones(db, coleccion_id),
        "errores": r_errores, "aviso": ""})


@router.post("/{coleccion_id}/series/{serie_id}/quitar")
async def quitar(coleccion_id: UUID, serie_id: UUID, db: AsyncSession = Depends(get_db)):
    await quitar_serie(db, coleccion_id, serie_id)
    await db.commit()
    return _redirigir(f"/ui/colecciones/{coleccion_id}?guardado=quitada")
