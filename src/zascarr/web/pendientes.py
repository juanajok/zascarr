"""
Router de la bandeja de pendientes (B2) — /ui/pendientes.

Archivos que el importer no supo clasificar (viven en _Unsorted/, ver
ReviewService). Cada acción es un endpoint HTMX que devuelve el
fragmento HTML que reemplaza la tarjeta o los resultados de búsqueda;
la lógica de negocio vive en ReviewService, no aquí.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import File, Series
from zascarr.services import registro_biblioteca
from zascarr.services.asignacion import (
    EstadoResultado,
    Resultado,
    servicio_por_defecto,
)
from zascarr.services.review import MOTIVO_COLISION_EDICION, ClavePendiente, ReviewService
from zascarr.services.revision_carpetas import (
    LIMITE_MAXIMO,
    RespuestaCarpetas,
    RevisionCarpetas,
    Suelto,
)
from zascarr.services.runtime_settings import RuntimeSettingsService
from zascarr.utils.cover import cached_image_response, extract_cover_thumbnail, puede_tener_portada
from zascarr.utils.naming import parse_comic_filename
from zascarr.web.routes import crear_templates


def _miles(n: int) -> str:
    """Formato de la vista: punto para los miles (1.322), no coma."""
    return f"{n:,}".replace(",", ".")


templates = crear_templates()
templates.env.filters["miles"] = _miles
logger = structlog.get_logger()

router = APIRouter(prefix="/ui/pendientes", tags=["ui"])


def _detected_label(filename: str) -> str:
    parsed = parse_comic_filename(filename)
    if not parsed.series:
        return "Sin detectar"
    return f"{parsed.series} #{parsed.issue_number}" if parsed.issue_number else parsed.series


def _suggestion(file: File) -> dict | None:
    """B12: mejor candidato guardado por el matcher (naming.py SÍ extrajo
    título+número pero no hubo serie que igualara con confianza) — se
    ofrece como sugerencia de un clic, nunca como autoasignación. El
    número de issue se prefilla del propio nombre de archivo cuando el
    parser lo detectó; si no, el coleccionista lo escribe a mano igual
    que en una búsqueda manual."""
    candidatos = (file.metadata_ or {}).get("candidates") or []
    if not candidatos:
        return None
    mejor = candidatos[0]
    parsed = parse_comic_filename(file.file_name)
    return {
        "series_id": mejor["series_id"],
        "title": mejor["title"],
        "start_year": mejor.get("start_year"),
        "score_pct": round(mejor["score"] * 100),
        "issue_number": parsed.issue_number or "",
    }


def _card(f: File) -> dict:
    return {
        "file": f,
        "detected": _detected_label(f.file_name),
        "suggestion": _suggestion(f),
        # U12: ausencia CONOCIDA (por la extensión, sin I/O): ni `<img>` ni petición ni bloque.
        "con_portada": puede_tener_portada(f.file_path,
                                           (f.metadata_ or {}).get("formato_contenido")),
        # B15: motivo de por qué este archivo sigue en revisión (p.ej. un
        # número compartido entre ediciones rechazado en una asignación).
        "motivo": (f.metadata_ or {}).get("review_motivo"),
    }


async def contar_carpetas(db: AsyncSession) -> int:
    """Cuántas carpetas ÚTILES tienen pendientes, con la MISMA definición que la pantalla de
    carpetas (`RevisionCarpetas`). Los grupos sin contexto son sueltos y no cuentan como
    carpeta. `limite=1` evita materializar la página."""
    return (await RevisionCarpetas(db).carpetas(limite=1)).totales.carpetas_utiles


def _enlace(parametro: str, clave: ClavePendiente) -> str:
    return f"/ui/pendientes?{urlencode({parametro: clave.a_texto()})}"


def _enlace_sueltos(parametro: str, clave: ClavePendiente) -> str:
    return f"/ui/pendientes/sueltos?{urlencode({parametro: clave.a_texto()})}"


def _card_suelto(s: Suelto) -> dict:
    """La tarjeta de U13b: el parser del nombre se comparte con la tarjeta existente."""
    return {"s": s, "detectado": _detected_label(s.nombre)}


def _rango(desde: int, hasta: int, total: int) -> dict:
    """«Mostrando X–Y de N»: una sola construcción para la página y para el refresco."""
    return {"desde": desde, "hasta": hasta, "total": total}


@router.get("", response_class=HTMLResponse)
async def index(
    request: Request,
    despues: str = Query(default=""),
    antes: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """La cola de pendientes, por cursor (U12). `despues` / `antes` son claves
    `imported_at|id`; una que no vale, o las dos a la vez, dan la primera página: una URL
    manipulada o vieja nunca es un error."""
    k_despues, k_antes = ClavePendiente.desde_texto(despues), ClavePendiente.desde_texto(antes)
    if k_despues and k_antes:
        k_despues = k_antes = None
    pagina = await ReviewService(db).pagina_de_pendientes(despues=k_despues, antes=k_antes)
    contexto: dict = {
        "cards": [_card(f) for f in pagina.archivos],
        "rango": _rango(pagina.desde, pagina.hasta, pagina.total),
        "siguiente": None, "anterior": None, "inicio": None, "primero": None, "ultimo": None}
    if pagina.archivos:
        primero = ClavePendiente.de(pagina.archivos[0])
        ultimo = ClavePendiente.de(pagina.archivos[-1])
        contexto.update(
            primero=primero.a_texto(), ultimo=ultimo.a_texto(),
            siguiente=_enlace("despues", ultimo) if pagina.hay_siguiente else None,
            anterior=_enlace("antes", primero) if pagina.hay_anterior else None,
            inicio="/ui/pendientes" if pagina.hay_anterior else None)
    resp = templates.TemplateResponse(request, "pendientes.html", contexto)
    resp.headers["Cache-Control"] = "no-store"      # la cola cambia con cada tarjeta resuelta
    return resp


@router.get("/carpetas/recuento", response_class=HTMLResponse)
async def recuento_de_carpetas(
    request: Request, db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """El enlace «Verlos por carpeta (N carpetas)», que la lista pide DESPUÉS de pintarse.

    Contar carpetas agrupa todos los pendientes en memoria (medido: ~100 ms con 1.322, frente a
    ~13 ms de toda la lista), así que no bloquea la carga de la bandeja. Si falla, o no hay
    carpetas, responde 204 y el enlace se queda como estaba, sin número: es un adorno del
    enlace, no puede romper nada."""
    try:
        n = await contar_carpetas(db)
    except Exception as exc:  # noqa: BLE001 — no debe afectar a la bandeja
        logger.warning("pendientes.recuento_de_carpetas_fallo", error=type(exc).__name__)
        return HTMLResponse(status_code=204)
    if not n:
        return HTMLResponse(status_code=204)
    resp = templates.TemplateResponse(request, "_pendientes_carpetas_enlace.html", {"carpetas": n})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/rango", response_class=HTMLResponse)
async def rango(
    request: Request,
    primero: str = Query(default=""),
    ultimo: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """«Mostrando X–Y de N» recalculado sobre el conjunto ACTUAL, para refrescar tras
    resolver una tarjeta sin recargar. `primero` y `ultimo` son las claves de los extremos
    de la página que se ve. Solo lectura."""
    k1, k2 = ClavePendiente.desde_texto(primero), ClavePendiente.desde_texto(ultimo)
    if k1 is None or k2 is None:
        return HTMLResponse(status_code=204)        # htmx no intercambia un 204
    servicio = ReviewService(db)
    total = await servicio.count_pending()
    delante = await servicio.contar_antes_de(k1)
    quedan = await servicio.contar_entre(k1, k2)
    # Una página vaciada no tiene rango: ni «desde» ni «hasta» (no «0–50»).
    r = _rango(delante + 1, delante + quedan, total) if quedan else _rango(0, 0, total)
    resp = templates.TemplateResponse(request, "_pendientes_rango.html", {"rango": r})
    resp.headers["Cache-Control"] = "no-store"
    return resp


#: Grupos por página en la vista HTML (el JSON admite hasta `LIMITE_MAXIMO`): una página corta se
#: pinta rápido en la Pi y se revisa con calma.
GRUPOS_POR_PAGINA = 50
_MARCADOR_ADOPCION = "_library_adoption_done"


def _vista_carpetas(r: RespuestaCarpetas, *, serie_actual: dict | None = None,
                    serie_aviso: str | None = None,
                    estado_nuevos: str | None = None) -> dict:
    """Prepara lo que pinta la plantilla SIN recalcular nada: señales, estados y etiquetas
    vienen del servicio (la misma respuesta que el JSON). Aquí solo se traducen los ids de
    `senales[].archivos` a nombres, que es presentación; `grupos[].archivos` contiene siempre
    a los afectados (contrato de 1a). La vista trabaja con `carpetas_utiles`, no con `grupos`:
    los grupos sin contexto son sueltos y no se paginan como carpetas."""
    grupos = []
    for g in r.grupos:
        nombres = {a.id: a.nombre for a in g.archivos}
        grupos.append({
            "g": g,
            "senales": [
                {"s": s, "afectados": [nombres[i] for i in s.archivos if i in nombres],
                 "sin_nombre": sum(1 for i in s.archivos if i not in nombres)}
                for s in g.senales
            ],
            "sin_mostrar": g.n_archivos - len(g.archivos),
            "sugerida_para_serie": bool(
                serie_actual and g.serie_sugerida is not None
                and str(g.serie_sugerida.series_id) == str(serie_actual["id"])
            ),
        })
    p = r.pagina
    total = r.totales.carpetas_utiles
    # Una página deja de existir si su offset ya cae fuera del conjunto actual. La
    # página 1 (offset 0) con cero grupos es el estado vacío normal, no una página rota.
    pagina_invalida = p.desplazamiento > 0 and p.desplazamiento >= total
    ultima = ((total - 1) // p.limite) * p.limite if total else 0
    desde = p.desplazamiento + 1 if r.grupos else 0
    return {
        "r": r,
        "grupos": grupos,
        "total_visible": r.totales.sin_serie + r.totales.serie_sugerida,
        "total_carpetas": total,
        "pagina_invalida": pagina_invalida,
        "ultima": ultima,
        "desde": desde,
        "hasta": p.desplazamiento + len(r.grupos),
        "anterior": (
            max(p.desplazamiento - p.limite, 0)
            if p.desplazamiento > 0 and not pagina_invalida else None
        ),
        "siguiente": (
            p.desplazamiento + p.limite if p.desplazamiento + p.limite < total else None
        ),
        "limite": p.limite,
        "serie_actual": serie_actual,
        "serie_aviso": serie_aviso,
        "estado_nuevos": estado_nuevos,
    }


async def _serie_del_filtro(db: AsyncSession, valor: str) -> tuple[dict | None, str | None]:
    """200 con aviso si `serie` no es UUID o no existe; nunca 422/500 por una URL."""
    if not valor:
        return None, None
    try:
        serie_id = UUID(valor)
    except (ValueError, TypeError):
        return None, ("No hemos encontrado esa serie. Se muestra la lista sin serie fijada. "
                      "Puede que se haya borrado o que el enlace esté incompleto.")
    fila = (await db.execute(
        select(Series.id, Series.title, Series.start_year).where(Series.id == serie_id)
    )).first()
    if fila is None:
        return None, ("No hemos encontrado esa serie. Se muestra la lista sin serie fijada. "
                      "Puede que se haya borrado o que el enlace esté incompleto.")
    return {"id": fila[0], "title": fila[1], "start_year": fila[2]}, None


async def _estado_nuevos(db: AsyncSession) -> str:
    """Disponibilidad de #326 sin disco: solo el marcador, leído con SELECT puro.
    `no_comprobado` = la lectura falló: no se sabe si la biblioteca está registrada."""
    if registro_biblioteca.estado_actual().en_marcha:
        return "en_marcha"
    try:
        if await RuntimeSettingsService(db).get_flag_sin_crear(_MARCADOR_ADOPCION):
            return "disponible"
    except Exception as exc:  # noqa: BLE001 — una oferta auxiliar no tumba la lista
        logger.warning("pendientes.marcador_fallo", error=type(exc).__name__)
        return "no_comprobado"      # no se afirma que no esté registrada
    return "no_disponible"


@router.get("/carpetas", response_class=HTMLResponse)
async def carpetas(
    request: Request,
    limite: int = Query(default=GRUPOS_POR_PAGINA, ge=1, le=LIMITE_MAXIMO),
    desplazamiento: int = Query(default=0, ge=0),
    serie: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Rebanada 1b: lo pendiente agrupado por carpeta, SOLO LECTURA. Misma respuesta que
    `GET /api/revision/carpetas`, con el filtro de lectura `solo_utiles`: los grupos sin
    contexto son sueltos y no se pintan como carpetas. No escribe, no mira el disco y no
    ofrece ninguna acción."""
    try:
        serie_valida = str(UUID(serie)) if serie else ""
    except (ValueError, TypeError):
        serie_valida = ""
    try:
        serie_actual, serie_aviso = await _serie_del_filtro(db, serie)
        servicio = RevisionCarpetas(db)
        respuesta = await servicio.carpetas(
            limite=limite, desplazamiento=desplazamiento, solo_utiles=True,
        )
        estado_nuevos = None
        if serie_actual is not None and not respuesta.grupos:
            estado_nuevos = await _estado_nuevos(db)
    except Exception as exc:  # noqa: BLE001 — un fallo no puede dejar recuentos a medias
        logger.warning("pendientes.carpetas_fallo", error=type(exc).__name__)
        resp = templates.TemplateResponse(
            request, "carpetas.html",
            {"error": True, "serie": serie_valida}, status_code=503,
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp
    resp = templates.TemplateResponse(request, "carpetas.html", _vista_carpetas(
        respuesta, serie_actual=serie_actual, serie_aviso=serie_aviso,
        estado_nuevos=estado_nuevos))
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/sueltos", response_class=HTMLResponse)
async def sueltos(
    request: Request,
    despues: str = Query(default=""),
    antes: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Cola de sueltos de A, solo lectura, por cursor (U13b).

    Muestra `metadata.candidates[0]` como sugerencia guardada, no aplicada. No usa
    `tradition_guess`, no consulta la serie candidata y no ofrece ninguna acción de escritura.
    Una clave inválida o las dos a la vez dan la primera página; un fallo de lectura devuelve
    503 sin recuentos parciales.
    """
    k_despues, k_antes = ClavePendiente.desde_texto(despues), ClavePendiente.desde_texto(antes)
    if k_despues and k_antes:
        k_despues = k_antes = None
    try:
        pagina = await RevisionCarpetas(db).pagina_de_sueltos(
            despues=k_despues, antes=k_antes,
        )
    except Exception as exc:  # noqa: BLE001 — un fallo no puede dejar recuentos a medias
        logger.warning("pendientes.sueltos_fallo", error=type(exc).__name__)
        resp = templates.TemplateResponse(
            request, "sueltos.html", {"error": True}, status_code=503,
        )
        resp.headers["Cache-Control"] = "no-store"
        return resp

    for s in pagina.archivos:
        if s.candidata_ilegible:
            # Sin ruta ni nombre: el aviso no debe filtrar datos de la biblioteca al log.
            logger.warning("pendientes.sueltos_candidata_ilegible")
    contexto = {
        "error": False,
        "sueltos": [_card_suelto(s) for s in pagina.archivos],
        "total": pagina.total,
        "total_texto": f"{pagina.total:,}".replace(",", "."),
        "total_a": pagina.total_a,
        "total_a_texto": f"{pagina.total_a:,}".replace(",", "."),
        "desde": pagina.desde,
        "hasta": pagina.hasta,
        "anterior": None,
        "siguiente": None,
    }
    if pagina.archivos:
        primero, ultimo = pagina.archivos[0].clave, pagina.archivos[-1].clave
        if pagina.hay_anterior:
            contexto["anterior"] = _enlace_sueltos("antes", primero)
        if pagina.hay_siguiente:
            contexto["siguiente"] = _enlace_sueltos("despues", ultimo)
    resp = templates.TemplateResponse(request, "sueltos.html", contexto)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.get("/{file_id}/portada")
async def portada(file_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    file = await db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = Path(file.file_path)
    # extract_cover_thumbnail es zipfile+Pillow, síncrono y bloqueante:
    # se manda a un hilo aparte para no congelar el event loop (M4).
    result = await asyncio.to_thread(extract_cover_thumbnail, path,
                                     (file.metadata_ or {}).get("formato_contenido"))
    if result is None:
        raise HTTPException(status_code=404, detail="Sin miniatura disponible")
    data, content_type = result
    etag = f'"{path.stat().st_mtime}"'
    return cached_image_response(request, data, content_type, etag)


@router.get("/{file_id}/buscar-serie", response_class=HTMLResponse)
async def buscar_serie(file_id: UUID, request: Request, q: str = "",
                        db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series_list = await ReviewService(db).search_series(q)
    return templates.TemplateResponse(
        request, "_resultados_serie.html", {"file_id": file_id, "series_list": series_list}
    )


@dataclass(frozen=True)
class Respuesta:
    """Cómo se le cuenta al coleccionista (y al cliente HTTP) cada resultado del servicio."""
    status: int
    texto: str = ""
    tipo: str = "warn"          # tipo de aviso (componentes de V2)
    asignado: bool = False      # ¿el archivo YA está asignado? (la tarjeta de «por revisar» sobra)


_TEXTO_ERROR_GENERICO = (
    "No se pudo asignar este archivo y el original no se ha tocado. Recarga la página y vuelve a "
    "intentarlo; si sigue igual, mira Estado."
)
_R = EstadoResultado
#: Resultado del servicio → respuesta. EXHAUSTIVA (una prueba recorre todos los estados) y sin
#: mostrar nunca `Resultado.motivo` tal cual: puede llevar rutas o textos del sistema.
RESPUESTAS: dict[EstadoResultado, Respuesta] = {
    _R.ASIGNADO: Respuesta(200, asignado=True),
    _R.YA_ASIGNADO: Respuesta(200, asignado=True),
    _R.ASIGNADO_LIMPIEZA_PENDIENTE: Respuesta(
        200, "Asignado. El archivo original sigue en la carpeta de revisión y se intentará retirar "
             "al reiniciar ZascArr.", "amber", asignado=True),
    _R.REPARACION_PENDIENTE: Respuesta(
        200, "La asignación necesita revisión; se ha conservado el original. ZascArr volverá a "
             "comprobarla al reiniciar.", "amber", asignado=True),
    _R.COLISION_EDICION: Respuesta(
        409, f"No se asigna: {MOTIVO_COLISION_EDICION}. Ese número ya existe como otra edición "
             "(por ejemplo una grapa y un recopilatorio). Elige otro número o revísalo a mano."),
    _R.NO_ENCONTRADO: Respuesta(400, "El archivo o la serie ya no existen. Recarga la página."),
    _R.DATOS_NO_VALIDOS: Respuesta(400, "Escribe el número del tebeo antes de confirmar."),
    _R.DESTINO_OCUPADO: Respuesta(
        409, "Otro archivo ocupó el nombre de destino mientras se copiaba. No se ha tocado nada; "
             "inténtalo de nuevo."),
    _R.YA_EN_CURSO: Respuesta(
        409, "Este archivo ya se está asignando. Espera unos segundos y recarga.", "info"),
    _R.PROPIEDAD_PERDIDA: Respuesta(
        409, "Este archivo ya se está asignando. Espera unos segundos y recarga.", "info"),
    _R.PENDIENTE: Respuesta(
        503, "No se pudo confirmar la asignación. Tus archivos están a salvo. Se reintentará al "
             "reiniciar ZascArr o al volver a asignar este archivo.", "amber"),
    _R.PENDIENTE_DE_COMPROBAR: Respuesta(
        503, "No se pudo comprobar si la asignación se guardó. No se ha borrado nada; se "
             "comprobará al reiniciar ZascArr o al volver a asignar este archivo.", "amber"),
    _R.ERROR: Respuesta(500, _TEXTO_ERROR_GENERICO),
}


#: Excepción que el servicio no controló: el endpoint NO sabe hasta dónde llegó (puede haber
#: confirmado e incluso retirado el original), así que no promete nada sobre los archivos.
RESPUESTA_INESPERADA = Respuesta(
    500, "No se pudo comprobar que la operación terminara. Recarga la página para consultar su "
         "estado antes de volver a intentarlo.")


def interpretar(r: Resultado) -> Respuesta:
    """Los recuperables no se esconden: «asignado con limpieza pendiente» y «reparación
    pendiente» son éxito con aviso; «pendiente» y «pendiente de comprobar» son 503 con la tarjeta
    delante. Un estado sin tratar nunca queda mudo."""
    return RESPUESTAS.get(r.estado, RESPUESTA_INESPERADA)


#: Tras asignar o ignorar, el menú vuelve a pedir SUS contadores a la BD (`/ui/_nav/estado`, que ya
#: los calcula a partir de los pendientes reales). No se resta uno a ciegas: el número lo da la
#: consulta, no la respuesta.
#: Va como un elemento inerte DENTRO de la respuesta que sustituye a la tarjeta y se pide al
#: cargarse.
#: NO como cabecera `HX-Trigger`: htmx 4 la despacha sobre el elemento que hizo la petición,
#: que ya no está en el DOM cuando la tarjeta se reemplaza (`outerHTML`), y un evento de un nodo
#: desconectado no llega a `body` (comprobado en navegador real con un clic; con `htmx.ajax` sin
#: elemento origen sí «funcionaba»).
#: U12: junto al menú se refresca «Mostrando X–Y de N» con el MISMO mecanismo (un elemento
#: inerte que se pide al cargarse). Toma las claves de los extremos de `#pend-clave`; si no
#: hay lista en pantalla, `#pend-rango` no existe y no se intercambia nada.
#: `hx-sync="#pend-rango:replace"`: dos resoluciones seguidas lanzan dos refrescos; el último
#: REEMPLAZA (aborta) al que sigue en vuelo, así que una respuesta antigua que llegue tarde no
#: sobrescribe el rango más reciente. Es del propio htmx, sin JavaScript nuestro.
RECONTAR_MENU = (
    '<span class="nav-recuento" hidden hx-get="/ui/_nav/estado" hx-trigger="load" '
    'hx-swap="none"></span>'
    '<span class="pend-recuento" hidden hx-get="/ui/pendientes/rango" hx-trigger="load" '
    'hx-include="#pend-clave" hx-target="#pend-rango" hx-swap="outerHTML" '
    'hx-sync="#pend-rango:replace"></span>')


def _es_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


@router.post("/{file_id}/asignar", response_class=HTMLResponse)
async def asignar(request: Request, file_id: UUID, series_id: UUID = Form(...),
                  issue_number: str = Form(...),
                  db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Asigna con el servicio RECUPERABLE (ADR 0006): copia verificada, confirmación en la BD y
    después se retira el original. El movimiento NO usa la sesión de la petición: el servicio
    confirma él mismo, así que la respuesta refleja lo que ya está guardado (el `commit` de
    `get_db` llega DESPUÉS de responder)."""
    if not (issue_number or "").strip():                       # sin tocar la BD
        r = Resultado(EstadoResultado.DATOS_NO_VALIDOS, "número vacío")
    else:
        try:
            r = await servicio_por_defecto().asignar(file_id, series_id, issue_number)
        except Exception as exc:  # noqa: BLE001 — nada llega al coleccionista como un 500 sin explicar
            logger.error("pendientes.asignar_fallo", error=type(exc).__name__)
            r = None
    resp = interpretar(r) if r is not None else RESPUESTA_INESPERADA
    aviso = {"tipo": resp.tipo, "texto": resp.texto}
    if resp.status == 200 and not resp.texto:
        return HTMLResponse(RECONTAR_MENU)                      # la tarjeta desaparece
    if resp.status == 200:                  # asignado, con un aviso que no debe perderse
        return templates.TemplateResponse(
            request, "_asignacion_aviso.html", {"aviso": aviso, "recontar_menu": RECONTAR_MENU})
    if not _es_htmx(request):
        raise HTTPException(status_code=resp.status, detail=resp.texto)
    # HTMX sustituye la TARJETA entera: se devuelve la tarjeta con el motivo y el aviso,
    # no un JSON en crudo.
    file = await db.get(File, file_id)
    if file is None:
        return templates.TemplateResponse(
            request, "_asignacion_aviso.html", {"aviso": aviso}, status_code=resp.status)
    return templates.TemplateResponse(
        request, "_tarjeta_pendiente.html", {"c": _card(file), "aviso": aviso},
        status_code=resp.status)


@router.post("/{file_id}/ignorar", response_class=HTMLResponse)
async def ignorar(file_id: UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await ReviewService(db).dismiss(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    # Se confirma AQUÍ y no en `get_db` (que lo hace DESPUÉS de responder): el menú pide su contador
    # en cuanto llega la respuesta y, si el commit aún no ha ocurrido, contaría el archivo ignorado.
    await db.commit()
    return HTMLResponse(RECONTAR_MENU)
