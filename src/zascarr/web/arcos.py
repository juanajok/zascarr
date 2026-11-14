"""BL-C4 (#151): pantallas de sagas y su CRUD manual."""
from __future__ import annotations

from urllib.parse import urlencode
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import async_session_factory, get_db
from zascarr.models import StoryArc
from zascarr.services.arcos import (
    agregar_numero,
    crear_arco,
    detalle_arco,
    editar_arco,
    eliminar_arco,
    listar_arcos,
    mover_numero,
    pedir_arco,
    quitar_numero,
)
from zascarr.services.arcos_fuentes import (
    buscar_arcos_fandom,
    importar_arco_fandom,
    previsualizar_arco_fandom,
)
from zascarr.services.comicbook_herald import ComicBookHeraldClient
from zascarr.services.fandom import FandomClient, FandomMaxLagError, FandomPayloadError
from zascarr.services.reading_orders.comicbookreadingorders import (
    HOSTS_PERMITIDOS as RO_HOSTS,
)
from zascarr.services.reading_orders.comicbookreadingorders import (
    RUTAS_PROHIBIDAS as RO_RUTAS,
)
from zascarr.services.reading_orders.comun import url_de_sitio_valida
from zascarr.services.reading_orders.continuity_guide import (
    HOSTS_PERMITIDOS as CG_HOSTS,
)
from zascarr.services.reading_orders.continuity_guide import (
    RUTAS_PROHIBIDAS as CG_RUTAS,
)
from zascarr.services.reconciliacion_lecturas import ORIGENES_DE_GUIA
from zascarr.utils.cache_http import CacheHttp
from zascarr.utils.cortesia import (
    NOMBRES_DE_FUENTE,
    CortesiaEnEspera,
    FuenteApagada,
    fuente_habilitada,
)
from zascarr.utils.peticiones import ErrorDePeticion
from zascarr.web.atribucion import atribucion_de_arco
from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
router = APIRouter(prefix="/ui/arcos", tags=["ui"])
templates = crear_templates()


async def _metadata_del_arco(db: AsyncSession, arco_id: UUID) -> dict:
    """El JSONB del arco (lo necesita la atribución de Fandom y la fuente de la guía).

    Se lee aparte porque `detalle_arco` (capa de servicios) no lo devuelve; una saga manual
    no tiene claves y estas vistas no pintan nada.
    """
    metadata = (await db.execute(
        select(StoryArc.metadata_).where(StoryArc.id == arco_id)
    )).scalar_one_or_none()
    return metadata if isinstance(metadata, dict) else {}


#: Hosts y rutas que puede tener la fuente de cada guía (misma allowlist que los extractores).
_HOSTS_DE_GUIA = {
    "reading_orders": (RO_HOSTS, RO_RUTAS),
    "continuity_guide": (CG_HOSTS, CG_RUTAS),
}


def fuente_de_guia(metadata: dict) -> dict[str, str] | None:
    """Fuente de una guía reconciliada (SCR3), validada como cualquier URL de sitio.

    El enlace es de navegación del usuario (no se descarga), pero se aplica la misma
    allowlist/validación que usa el extractor para que un `metadata_` manipulado no pinte un
    `javascript:` ni un host ajeno (SecOps m-2/c-4).
    """
    origen = metadata.get("origen")
    url = metadata.get("url")
    if origen not in ORIGENES_DE_GUIA or not isinstance(url, str) or len(url) > 500:
        return None
    hosts, rutas = _HOSTS_DE_GUIA[str(origen)]
    if not url_de_sitio_valida(url, hosts, rutas_prohibidas=rutas, exigir_pagina=True):
        return None
    return {"url": url, "nombre": NOMBRES_DE_FUENTE.get(str(origen), str(origen))}


def _respuesta(request: Request, plantilla: str, contexto: dict) -> HTMLResponse:
    resp = templates.TemplateResponse(request, plantilla, contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


def _redirigir(destino: str) -> RedirectResponse:
    return RedirectResponse(destino, status_code=303)


async def _novedades_de_herald() -> list:
    """Las 5 últimas guías del feed de Comic Book Herald, o [] (fuente apagada/fallo).

    Solo se llama con la fuente encendida; un fallo de red/robots no pinta nada (sin error).
    """
    if not fuente_habilitada("comic_book_herald"):
        return []
    try:
        async with ComicBookHeraldClient(CacheHttp(async_session_factory)) as cliente:
            return (await cliente.novedades())[:5]
    except (FuenteApagada, CortesiaEnEspera):
        return []
    except Exception:
        logger.warning("comicbook_herald.ui_sin_novedades")
        return []


@router.get("", response_class=HTMLResponse)
async def arcos(request: Request, pagina: int = Query(default=1, ge=1),
                guardado: str = Query(default=""),
                db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    return _respuesta(request, "arcos.html", {
        "pagina": await listar_arcos(db, pagina),
        "herald_items": await _novedades_de_herald(),
        "aviso": {
            "creada": "Saga creada.",
            "guardada": "Saga guardada.",
            "borrada": "Saga eliminada. No se ha borrado ningún número ni archivo.",
            "numero": "Número añadido a la saga.",
            "quitado": "Número quitado de la saga; el número sigue en tu biblioteca.",
            "orden": "Orden actualizado.",
        }.get(guardado, ""),
    })


@router.get("/nueva", response_class=HTMLResponse)
async def nueva_arco_form(request: Request) -> HTMLResponse:
    return _respuesta(request, "editar_arco.html", {
        "arco": None, "valores": {"title": "", "description": "", "is_crossover": False},
        "errores": {}, "accion": "/ui/arcos/nueva",
    })


@router.post("/nueva", response_class=HTMLResponse)
async def nueva_arco_guardar(request: Request,
                             title: str = Form(default=""),
                             description: str = Form(default=""),
                             is_crossover: bool = Form(default=False),
                             db: AsyncSession = Depends(get_db)) -> Response:
    resultado = await crear_arco(
        db, title=title, description=description, is_crossover=is_crossover)
    if not resultado.ok:
        await db.rollback()
        return _respuesta(request, "editar_arco.html", {
            "arco": None, "valores": {"title": title, "description": description,
                                      "is_crossover": is_crossover},
            "errores": resultado.errores, "accion": "/ui/arcos/nueva",
        })
    await db.commit()
    return _redirigir(f"/ui/arcos/{resultado.arco.id}?guardado=creada")


ERROR_FANDOM = ("No se pudo consultar DC Database. Inténtalo de nuevo más tarde.")


async def _fuente_fandom_activa() -> bool:
    return bool(fuente_habilitada("fandom_dc"))


@router.get("/buscar", response_class=HTMLResponse)
async def buscar_arcos(request: Request, q: str = Query(default=""),
                       db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    consulta = (q or "").strip()[:200]
    contexto = {"q": consulta, "resultados": [], "errores": {}, "aviso": ""}
    if not await _fuente_fandom_activa():
        contexto["errores"] = {"general": "La fuente DC Database está apagada en Ajustes."}
        return _respuesta(request, "buscar_arcos.html", contexto)
    if consulta:
        try:
            async with FandomClient(
                    "dc.fandom.com", cache=CacheHttp(async_session_factory)) as cliente:
                contexto["resultados"] = await buscar_arcos_fandom(consulta, cliente)
        except (CortesiaEnEspera, FuenteApagada, FandomMaxLagError,
                FandomPayloadError, ErrorDePeticion):
            contexto["errores"] = {"general": ERROR_FANDOM}
        except Exception:
            logger.exception("arcos.buscar_fandom_failed")
            contexto["errores"] = {"general": ERROR_FANDOM}
    return _respuesta(request, "buscar_arcos.html", contexto)


@router.get("/buscar/preview", response_class=HTMLResponse)
async def previsualizar_arco(request: Request, page_title: str = Query(default=""),
                             db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    titulo = (page_title or "").strip()[:255]
    contexto = {"page_title": titulo, "previa": None, "errores": {}, "aviso": "",
                "atribucion_fandom": atribucion_de_arco({"fandom_dc": titulo})}
    if not titulo:
        contexto["errores"] = {"general": "Falta el título de la página del arco."}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    if not await _fuente_fandom_activa():
        contexto["errores"] = {"general": "La fuente DC Database está apagada en Ajustes."}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    try:
        async with FandomClient(
                "dc.fandom.com", cache=CacheHttp(async_session_factory)) as cliente:
            previa = await previsualizar_arco_fandom(db, titulo, cliente)
        if previa is None:
            contexto["errores"] = {"general": "No se encontró ese arco en DC Database."}
        else:
            contexto["previa"] = previa
    except (CortesiaEnEspera, FuenteApagada, FandomMaxLagError,
            FandomPayloadError, ErrorDePeticion):
        contexto["errores"] = {"general": ERROR_FANDOM}
    except Exception:
        logger.exception("arcos.previa_fandom_failed")
        contexto["errores"] = {"general": ERROR_FANDOM}
    return _respuesta(request, "previa_arco_fuente.html", contexto)


@router.post("/buscar/importar", response_class=HTMLResponse)
async def importar_arco(request: Request, page_title: str = Form(default=""),
                        confirmo: str = Form(default="0"),
                        db: AsyncSession = Depends(get_db)) -> Response:
    titulo = (page_title or "").strip()[:255]
    if not titulo:
        return _respuesta(request, "previa_arco_fuente.html", {
            "page_title": titulo, "previa": None,
            "errores": {"general": "Falta el título de la página del arco."}, "aviso": ""})
    if confirmo != "1":
        return _respuesta(request, "previa_arco_fuente.html", {
            "page_title": titulo, "previa": None,
            "errores": {"general": "Marca la confirmación antes de importar la saga."},
            "aviso": ""})
    if not await _fuente_fandom_activa():
        return _respuesta(request, "previa_arco_fuente.html", {
            "page_title": titulo, "previa": None,
            "errores": {"general": "La fuente DC Database está apagada en Ajustes."},
            "aviso": ""})
    try:
        async with FandomClient(
                "dc.fandom.com", cache=CacheHttp(async_session_factory)) as cliente:
            resultado = await importar_arco_fandom(db, titulo, cliente)
    except (CortesiaEnEspera, FuenteApagada, FandomMaxLagError,
            FandomPayloadError, ErrorDePeticion):
        resultado = None
    except Exception:
        logger.exception("arcos.importar_fandom_failed")
        resultado = None
    if resultado is None:
        await db.rollback()
        return _respuesta(request, "previa_arco_fuente.html", {
            "page_title": titulo, "previa": None,
            "errores": {"general": "No se pudo importar la saga. Inténtalo de nuevo."},
            "aviso": ""})
    await db.commit()
    return _redirigir(f"/ui/arcos/{resultado.arco_id}?guardado=importada")


@router.get("/{arco_id}", response_class=HTMLResponse)
async def arco(arco_id: UUID, request: Request, guardado: str = Query(default=""),
               anadidos: int = Query(default=0, ge=0),
               ya_pedidos: int = Query(default=0, ge=0),
               en_biblioteca: int = Query(default=0, ge=0),
               db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    detalle = await detalle_arco(db, arco_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Arco no encontrado")
    metadata = await _metadata_del_arco(db, arco_id)
    return _respuesta(request, "arco.html", {
        "arco": detalle,
        "atribucion_fandom": atribucion_de_arco(metadata),
        "fuente_guia": fuente_de_guia(metadata),
        "aviso": {
            "creada": "Saga creada.", "guardada": "Saga guardada.",
            "numero": "Número añadido a la saga.",
            "quitado": "Número quitado de la saga; sigue en tu biblioteca.",
            "orden": "Orden actualizado.",
            "importada": "Saga importada desde Fandom; solo se enlazaron números de tu biblioteca.",
        }.get(guardado, ""),
        # El formulario de «Añadir un número» pinta siempre sus errores/valores: en el GET,
        # vacíos; el POST de error los rellena para no perder lo escrito.
        "errores": {}, "valores": {"serie": "", "numero": "", "orden": ""},
        "pedido": {"anadidos": anadidos, "ya_pedidos": ya_pedidos,
                   "en_biblioteca": en_biblioteca} if guardado == "pedido" else None,
    })


@router.post("/{arco_id}/pedir")
async def pedir_arco_completo(arco_id: UUID,
                              db: AsyncSession = Depends(get_db)) -> Response:
    """BL-D7: pide al wishlist los números de la saga que aún falten."""
    resultado = await pedir_arco(db, arco_id)
    if not resultado.ok:
        raise HTTPException(status_code=404, detail=resultado.errores.get(
            "general", "No se pudo pedir la saga"))
    await db.commit()
    consulta = urlencode({"guardado": "pedido", "anadidos": resultado.anadidos,
                          "ya_pedidos": resultado.ya_pedidos,
                          "en_biblioteca": resultado.en_biblioteca})
    return _redirigir(f"/ui/arcos/{arco_id}?{consulta}")


@router.get("/{arco_id}/editar", response_class=HTMLResponse)
async def editar_arco_form(arco_id: UUID, request: Request,
                           db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    detalle = await detalle_arco(db, arco_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Arco no encontrado")
    return _respuesta(request, "editar_arco.html", {
        "arco": detalle,
        "valores": {"title": detalle.title, "description": detalle.description or "",
                    "is_crossover": detalle.is_crossover},
        "errores": {}, "accion": f"/ui/arcos/{arco_id}/editar",
    })


@router.post("/{arco_id}/editar", response_class=HTMLResponse)
async def editar_arco_guardar(arco_id: UUID, request: Request,
                              title: str = Form(default=""),
                              description: str = Form(default=""),
                              is_crossover: bool = Form(default=False),
                              db: AsyncSession = Depends(get_db)) -> Response:
    resultado = await editar_arco(
        db, arco_id, title=title, description=description, is_crossover=is_crossover)
    if not resultado.ok:
        await db.rollback()
        return _respuesta(request, "editar_arco.html", {
            "arco": resultado.arco,
            "valores": {"title": title, "description": description,
                        "is_crossover": is_crossover},
            "errores": resultado.errores, "accion": f"/ui/arcos/{arco_id}/editar",
        })
    await db.commit()
    return _redirigir(f"/ui/arcos/{arco_id}?guardado=guardada")


@router.get("/{arco_id}/eliminar", response_class=HTMLResponse)
async def eliminar_arco_form(arco_id: UUID, request: Request,
                             db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    detalle = await detalle_arco(db, arco_id)
    if detalle is None:
        raise HTTPException(status_code=404, detail="Arco no encontrado")
    return _respuesta(request, "eliminar_arco.html", {"arco": detalle})


@router.post("/{arco_id}/eliminar")
async def eliminar_arco_confirmar(arco_id: UUID,
                                  db: AsyncSession = Depends(get_db)) -> Response:
    if not await eliminar_arco(db, arco_id):
        raise HTTPException(status_code=404, detail="Arco no encontrado")
    await db.commit()
    return _redirigir("/ui/arcos?guardado=borrada")


@router.post("/{arco_id}/numeros")
async def anadir_numero(arco_id: UUID, request: Request,
                        serie: str = Form(default=""), numero: str = Form(default=""),
                        orden: str = Form(default=""),
                        db: AsyncSession = Depends(get_db)) -> Response:
    posicion = None
    if orden.strip().isdigit():
        posicion = int(orden.strip())
    resultado = await agregar_numero(
        db, arco_id, serie=serie, numero=numero, orden=posicion)
    if not resultado.ok:
        await db.rollback()
        detalle = await detalle_arco(db, arco_id)
        if detalle is None:
            raise HTTPException(status_code=404, detail="Arco no encontrado")
        metadata = await _metadata_del_arco(db, arco_id)
        return _respuesta(request, "arco.html", {
            "arco": detalle,
            "atribucion_fandom": atribucion_de_arco(metadata),
            "fuente_guia": fuente_de_guia(metadata),
            "aviso": "",
            "errores": resultado.errores,
            "valores": {"serie": serie, "numero": numero, "orden": orden},
        })
    await db.commit()
    return _redirigir(f"/ui/arcos/{arco_id}?guardado=numero")


@router.post("/{arco_id}/numeros/{issue_id}/quitar")
async def quitar_numero_arco(arco_id: UUID, issue_id: UUID,
                             db: AsyncSession = Depends(get_db)) -> Response:
    if not await quitar_numero(db, arco_id, issue_id):
        raise HTTPException(status_code=404, detail="Ese número no está en la saga")
    await db.commit()
    return _redirigir(f"/ui/arcos/{arco_id}?guardado=quitado")


@router.post("/{arco_id}/numeros/{issue_id}/mover")
async def mover_numero_arco(arco_id: UUID, issue_id: UUID,
                            subir: bool = Form(default=False),
                            db: AsyncSession = Depends(get_db)) -> Response:
    await mover_numero(db, arco_id, issue_id, subir=bool(subir))
    await db.commit()
    return _redirigir(f"/ui/arcos/{arco_id}?guardado=orden")
