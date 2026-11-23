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
    primera_portada_de_arco,
    quitar_numero,
)
from zascarr.services.arcos_fuentes import (
    buscar_arcos_fandom,
    importar_arco_fandom,
    previsualizar_arco_fandom,
)
from zascarr.services.comicbook_herald import ComicBookHeraldClient
from zascarr.services.fandom import FandomClient, FandomMaxLagError, FandomPayloadError
from zascarr.services.reading_orders import (
    ContinuityGuideExtractor,
    ReadingOrdersExtractor,
)
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
from zascarr.services.reconciliacion_lecturas import (
    ORIGENES_DE_GUIA,
    leer_y_reconciliar,
)
from zascarr.utils.cache_http import CacheHttp
from zascarr.utils.cortesia import (
    NOMBRES_DE_FUENTE,
    CortesiaEnEspera,
    FuenteApagada,
    fuente_habilitada,
)
from zascarr.utils.peticiones import ErrorDePeticion
from zascarr.utils.robots import AccesoProhibidoPorRobots
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


async def _novedades_de_herald(*, espera_max_s: float = 30.0) -> list:
    """Las 5 últimas guías del feed de Comic Book Herald, o [] (fuente apagada/fallo).

    La llamada desde el GET de Sagas es **perezosa** (#854): el endpoint que la usa pide un
    presupuesto corto (10 s) para que un feed lento no retenga la página.
    """
    if not fuente_habilitada("comic_book_herald"):
        return []
    try:
        async with ComicBookHeraldClient(
                CacheHttp(async_session_factory), espera_max_s=espera_max_s) as cliente:
            return (await cliente.novedades())[:5]
    except (FuenteApagada, CortesiaEnEspera):
        return []
    except Exception:
        logger.warning("comicbook_herald.ui_sin_novedades")
        return []


#: Motivos de la reconciliación en llano (nunca códigos internos en la UI).
MOTIVOS_DE_GUIA = {
    "sin_referencia": "referencias que no se entendieron",
    "no_aplica": "tomos o volúmenes que no son grapas",
    "serie_no_encontrada": "series que no están en tu biblioteca",
    "ambiguo": "referencias ambiguas",
    "numero_no_encontrado": "números que no tienes",
    "tope": "referencias por encima del límite",
}
_EXTRACTORES_DE_GUIA = {
    "reading_orders": ReadingOrdersExtractor,
    "continuity_guide": ContinuityGuideExtractor,
}


def _contexto_importar_guia(*, fuente: str = "reading_orders", url: str = "",
                            errores: dict | None = None,
                            valores: dict | None = None) -> dict:
    fuente = fuente if fuente in ORIGENES_DE_GUIA else "reading_orders"
    return {
        "fuente": fuente,
        "url": url,
        "errores": errores or {},
        "valores": valores or {"fuente": fuente, "url": url},
        "fuente_apagada": not fuente_habilitada(fuente),
    }


def _respuesta_importar(request: Request, contexto: dict) -> HTMLResponse:
    """En htmx se cambia solo el bloque de resultado; sin htmx, la página completa."""
    es_htmx = request.headers.get("hx-request", "").lower() == "true"
    return _respuesta(request,
                      "_importar_guia_resultado.html" if es_htmx else "importar_guia.html",
                      contexto)


def _motivos_legibles(motivos) -> str:
    partes = []
    for clave, cantidad in motivos:
        etiqueta = MOTIVOS_DE_GUIA.get(str(clave), "otras referencias")
        partes.append(f"{cantidad} {etiqueta}")
    return "; ".join(partes)


@router.get("/novedades-herald", response_class=HTMLResponse)
async def novedades_herald(request: Request) -> HTMLResponse:
    """Parcial perezoso de «Novedades de Comic Book Herald» (#854).

    Fuente apagada o cualquier fallo ⇒ 200 con cuerpo vacío: la sección se oculta con `:has`
    y no se pinta un error. La respuesta nunca se cachea en el navegador (la caché del feed
    vive en `http_cache`, 6 h).
    """
    items = await _novedades_de_herald(espera_max_s=10.0)
    return _respuesta(request, "_novedades_herald.html", {"herald_items": items})


@router.get("/importar-guia", response_class=HTMLResponse)
async def importar_guia_form(request: Request,
                             fuente: str = Query(default="reading_orders"),
                             url: str = Query(default="")) -> HTMLResponse:
    return _respuesta(request, "importar_guia.html",
                      _contexto_importar_guia(fuente=fuente, url=url[:500]))


@router.post("/importar-guia", response_class=HTMLResponse)
async def importar_guia(request: Request, fuente: str = Form(default=""),
                        url: str = Form(default=""),
                        db: AsyncSession = Depends(get_db)) -> Response:
    """Importa una guía de SCR3 y reconcilia con la biblioteca (historia #843)."""
    url = (url or "").strip()[:500]
    if fuente not in ORIGENES_DE_GUIA:
        return _respuesta_importar(request, _contexto_importar_guia(
            url=url, valores={"fuente": fuente, "url": url},
            errores={"general": "Elige una de las dos fuentes de guías."}))
    hosts, rutas = _HOSTS_DE_GUIA[fuente]
    if not url_de_sitio_valida(url, hosts, rutas_prohibidas=rutas, exigir_pagina=True):
        return _respuesta_importar(request, _contexto_importar_guia(
            fuente=fuente, url=url,
            errores={"general": "Esa dirección no es una guía válida de esa fuente. "
                                "Copia la URL de la guía (https), sin parámetros."}))
    if not fuente_habilitada(fuente):
        return _respuesta_importar(request, _contexto_importar_guia(
            fuente=fuente, url=url,
            errores={"general": "Esa fuente está apagada en Ajustes. Enciéndela para "
                                "importar la guía."}))
    nombre = NOMBRES_DE_FUENTE.get(fuente, fuente)
    try:
        extractor = _EXTRACTORES_DE_GUIA[fuente](CacheHttp(async_session_factory))
        async with extractor:
            resultado = await leer_y_reconciliar(db, extractor, url)
        if resultado is None or resultado.arco_id is None:
            await db.rollback()
            return _respuesta_importar(request, _contexto_importar_guia(
                fuente=fuente, url=url,
                errores={"general": "La guía no tiene entradas legibles o no se pudo leer. "
                                    "Comprueba la dirección y que la fuente siga encendida."}))
        # El commit también va dentro del try: si falla, se revierte y se avisa en llano.
        await db.commit()
    except CortesiaEnEspera as exc:
        await db.rollback()
        segundos = max(1, round(exc.espera_estimada_s))
        return _respuesta_importar(request, _contexto_importar_guia(
            fuente=fuente, url=url,
            errores={"general": f"{nombre} pide esperar ~{segundos} s antes de otra "
                                "consulta. Inténtalo de nuevo en un momento."}))
    except AccesoProhibidoPorRobots:
        await db.rollback()
        return _respuesta_importar(request, _contexto_importar_guia(
            fuente=fuente, url=url,
            errores={"general": f"El robots.txt de {nombre} no permite leer esa guía."}))
    except ErrorDePeticion:
        await db.rollback()
        return _respuesta_importar(request, _contexto_importar_guia(
            fuente=fuente, url=url,
            errores={"general": f"No se pudo leer la guía de {nombre}. Inténtalo de nuevo "
                                "más tarde."}))
    except Exception as exc:
        # m-2: sin traza ni URL/parámetros; solo tipo y fuente (el mensaje ya es llano).
        logger.error("arcos.importar_guia_failed", fuente=fuente,
                     error=type(exc).__name__)
        await db.rollback()
        return _respuesta_importar(request, _contexto_importar_guia(
            fuente=fuente, url=url,
            errores={"general": "No se pudo importar la guía. Inténtalo de nuevo."}))
    motivos = _motivos_legibles(resultado.motivos)[:400]
    consulta = urlencode({
        "importada": "1",
        "enlazados": resultado.enlazados,
        "omitidos": resultado.omitidos,
        "motivos": motivos,
    })
    destino = f"/ui/arcos/{resultado.arco_id}?{consulta}"
    respuesta = _redirigir(destino)
    if request.headers.get("hx-request", "").lower() == "true":
        respuesta.headers["HX-Redirect"] = destino
    return respuesta


@router.get("", response_class=HTMLResponse)
async def arcos(request: Request, pagina: int = Query(default=1, ge=1),
                guardado: str = Query(default=""),
                db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    return _respuesta(request, "arcos.html", {
        "pagina": await listar_arcos(db, pagina),
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
    # UXA-17 (#1134): vacío, apagada, espera y fallo tienen cada uno su salida.
    contexto = {"q": consulta, "resultados": [], "errores": {}, "aviso": "", "estado": ""}
    if not await _fuente_fandom_activa():
        contexto["estado"] = "apagada"
        return _respuesta(request, "buscar_arcos.html", contexto)
    if consulta:
        try:
            async with FandomClient(
                    "dc.fandom.com", cache=CacheHttp(async_session_factory)) as cliente:
                contexto["resultados"] = await buscar_arcos_fandom(consulta, cliente)
            contexto["estado"] = "ok" if contexto["resultados"] else "vacio"
        except CortesiaEnEspera:
            contexto["estado"] = "espera"
        except FuenteApagada:
            contexto["estado"] = "apagada"
        except (FandomMaxLagError, FandomPayloadError, ErrorDePeticion):
            contexto["estado"] = "fallo"
        except Exception:
            logger.exception("arcos.buscar_fandom_failed")
            contexto["estado"] = "fallo"
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
    contexto = {"page_title": titulo, "previa": None, "errores": {}, "aviso": ""}
    if not titulo:
        contexto["errores"] = {"general": "Falta el título de la página del arco."}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    if not await _fuente_fandom_activa():
        contexto["errores"] = {"general": "La fuente DC Database está apagada en Ajustes."}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    try:
        async with FandomClient(
                "dc.fandom.com", cache=CacheHttp(async_session_factory)) as cliente:
            # Se conserva la previsualización para cualquier error de validación o de
            # importación: el coleccionista no tiene que volver a buscar.
            previa = await previsualizar_arco_fandom(db, titulo, cliente)
            contexto["previa"] = previa
            if previa is None:
                contexto["errores"] = {"general": "No se encontró ese arco en DC Database."}
                return _respuesta(request, "previa_arco_fuente.html", contexto)
            if confirmo != "1":
                contexto["errores"] = {
                    "general": "Marca la confirmación antes de importar la saga."}
                return _respuesta(request, "previa_arco_fuente.html", contexto)
            resultado = await importar_arco_fandom(db, titulo, cliente)
    except (CortesiaEnEspera, FuenteApagada, FandomMaxLagError,
            FandomPayloadError, ErrorDePeticion):
        await db.rollback()
        contexto["errores"] = {"general": ERROR_FANDOM}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    except Exception:
        logger.exception("arcos.importar_fandom_failed")
        await db.rollback()
        contexto["errores"] = {"general": "No se pudo importar la saga. Inténtalo de nuevo."}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    if resultado is None:
        await db.rollback()
        contexto["errores"] = {"general": "No se pudo importar la saga. Inténtalo de nuevo."}
        return _respuesta(request, "previa_arco_fuente.html", contexto)
    await db.commit()
    return _redirigir(f"/ui/arcos/{resultado.arco_id}?guardado=importada")


@router.get("/{arco_id}/portada.jpg")
async def portada_de_arco(arco_id: UUID, db: AsyncSession = Depends(get_db)) -> Response:
    """Miniatura de la saga desde su primer número miembro; nunca una URL externa directa."""
    fila = await primera_portada_de_arco(db, arco_id)
    if fila is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    series_id, issue_id = fila
    return RedirectResponse(
        f"/ui/series/{series_id}/numero/{issue_id}/portada.jpg", status_code=307)


@router.get("/{arco_id}", response_class=HTMLResponse)
async def arco(arco_id: UUID, request: Request, guardado: str = Query(default=""),
               importada: str = Query(default=""),
               enlazados: int = Query(default=0, ge=0),
               omitidos: int = Query(default=0, ge=0),
               motivos: str = Query(default=""),
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
        "importada": {"enlazados": enlazados, "omitidos": omitidos,
                      "motivos": motivos[:400]} if importada == "1" else None,
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
        # Tras el rollback el arco del resultado caduca y la plantilla lo leía fuera del contexto
        # asíncrono (500 en cualquier error): se vuelve a leer, como en el formulario.
        return _respuesta(request, "editar_arco.html", {
            "arco": await detalle_arco(db, arco_id),
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
