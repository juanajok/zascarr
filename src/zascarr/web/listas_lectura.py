"""#1080: UI de listas de lectura curadas (números concretos)."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.services import listas_lectura as servicio
from zascarr.web.routes import crear_templates

router = APIRouter(prefix="/ui/listas", tags=["ui"])
templates = crear_templates()


def _respuesta(request: Request, plantilla: str, contexto: dict,
               status: int = 200) -> HTMLResponse:
    respuesta = templates.TemplateResponse(request, plantilla, contexto, status_code=status)
    respuesta.headers["Cache-Control"] = "no-store"
    return respuesta


def _hecho(request: Request, destino: str):
    """HTMX no recarga: HX-Redirect; navegación normal: 303."""
    if request.headers.get("HX-Request") == "true":
        return Response(status_code=204, headers={"HX-Redirect": destino,
                                                  "Cache-Control": "no-store"})
    return RedirectResponse(destino, status_code=303)


@router.get("", response_class=HTMLResponse)
async def indice(request: Request, guardado: str = "", db: AsyncSession = Depends(get_db)):
    return _respuesta(request, "listas.html", {
        "listas": await servicio.listar(db),
        "aviso": {
            "creada": "Lista creada.",
            "guardada": "Lista guardada.",
            "borrada": "Lista borrada. Los números siguen en tu biblioteca.",
        }.get(guardado, ""),
    })


@router.post("/nueva")
async def nueva(request: Request, name: str = Form(""), description: str = Form(""),
                db: AsyncSession = Depends(get_db)):
    try:
        lista = await servicio.crear(db, name, description)
    except servicio.ListaInvalidaError as exc:
        return _respuesta(request, "listas.html", {
            "listas": await servicio.listar(db), "aviso": "", "error": str(exc),
            "valores": {"name": name, "description": description}}, status=400)
    await db.commit()
    return _hecho(request, f"/ui/listas/{lista.id}?guardado=creada")


@router.post("/anadir")
async def anadir_a_lista(request: Request, lista_id: str = Form(""),
                         issue_id: str = Form(""), db: AsyncSession = Depends(get_db)):
    try:
        await servicio.anadir(db, UUID(lista_id), UUID(issue_id))
        await db.commit()
    except (ValueError, servicio.ListaInvalidaError):
        return _hecho(request, "/ui/series?guardado=error") if not issue_id else _hecho(
            request, f"/ui/listas/{lista_id}?error=duplicado")
    return _hecho(request, f"/ui/listas/{lista_id}?guardado=anadido")


@router.get("/opciones/{serie_id}/{issue_id}", response_class=HTMLResponse)
async def opciones(request: Request, issue_id: UUID, serie_id: UUID,
                   db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """#1080: fragmento perezoso de «Añadir a lista» desde la ficha del número."""
    return _respuesta(request, "_lista_opciones.html", {
        "listas": await servicio.listar(db), "issue_id": str(issue_id),
        "serie_id": str(serie_id)})


@router.get("/{lista_id}", response_class=HTMLResponse)
async def detalle(request: Request, lista_id: UUID, guardado: str = "",
                  error: str = "", db: AsyncSession = Depends(get_db)):
    datos = await servicio.detalle(db, lista_id)
    if datos is None:
        return _respuesta(request, "lista_detalle.html", {
            "lista": None, "items": [], "total": 0, "leidos": 0,
            "aviso": "", "error": "La lista ya no existe."}, status=404)
    return _respuesta(request, "lista_detalle.html", {
        **datos,
        "aviso": {
            "creada": "Lista creada.",
            "guardada": "Lista guardada.",
            "anadido": "Número añadido a la lista.",
            "quitado": "Número quitado de la lista.",
            "movido": "Orden actualizado.",
        }.get(guardado, ""),
        "error": {
            "duplicado": "Ese número ya está en la lista.",
        }.get(error, ""),
    })


@router.post("/{lista_id}/editar")
async def editar(request: Request, lista_id: UUID, name: str = Form(""),
                 description: str = Form(""), db: AsyncSession = Depends(get_db)):
    try:
        await servicio.renombrar(db, lista_id, name, description)
        await db.commit()
    except servicio.ListaInvalidaError as exc:
        datos = await servicio.detalle(db, lista_id)
        if datos is None:
            return _respuesta(request, "lista_detalle.html", {"lista": None},
                              status=404)
        return _respuesta(request, "lista_detalle.html", {
            **datos, "aviso": "", "error": str(exc),
            "valores": {"name": name, "description": description}}, status=400)
    return _hecho(request, f"/ui/listas/{lista_id}?guardado=guardada")


@router.post("/{lista_id}/borrar")
async def borrar(request: Request, lista_id: UUID, db: AsyncSession = Depends(get_db)):
    await servicio.borrar(db, lista_id)
    await db.commit()
    return _hecho(request, "/ui/listas?guardado=borrada")


@router.post("/{lista_id}/quitar/{issue_id}")
async def quitar(request: Request, lista_id: UUID, issue_id: UUID,
                 db: AsyncSession = Depends(get_db)):
    await servicio.quitar(db, lista_id, issue_id)
    await db.commit()
    return _hecho(request, f"/ui/listas/{lista_id}?guardado=quitado")


@router.post("/{lista_id}/mover/{issue_id}/{direccion}")
async def mover(request: Request, lista_id: UUID, issue_id: UUID, direccion: str,
                db: AsyncSession = Depends(get_db)):
    await servicio.mover(db, lista_id, issue_id, direccion)
    await db.commit()
    return _hecho(request, f"/ui/listas/{lista_id}?guardado=movido")
