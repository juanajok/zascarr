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
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import File
from zascarr.services.asignacion import (
    EstadoResultado,
    Resultado,
    servicio_por_defecto,
)
from zascarr.services.review import MOTIVO_COLISION_EDICION, ReviewService
from zascarr.utils.cover import cached_image_response, extract_cover_thumbnail
from zascarr.utils.naming import parse_comic_filename
from zascarr.web.routes import crear_templates

templates = crear_templates()
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
        # B15: motivo de por qué este archivo sigue en revisión (p.ej. un
        # número compartido entre ediciones rechazado en una asignación).
        "motivo": (f.metadata_ or {}).get("review_motivo"),
    }


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    files = await ReviewService(db).pending_files()
    cards = [_card(f) for f in files]
    return templates.TemplateResponse(request, "pendientes.html", {"cards": cards})


@router.get("/{file_id}/portada")
async def portada(file_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> Response:
    file = await db.get(File, file_id)
    if not file:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")
    path = Path(file.file_path)
    # extract_cover_thumbnail es zipfile+Pillow, síncrono y bloqueante:
    # se manda a un hilo aparte para no congelar el event loop (M4).
    result = await asyncio.to_thread(extract_cover_thumbnail, path)
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
RECONTAR_MENU = (
    '<span class="nav-recuento" hidden hx-get="/ui/_nav/estado" hx-trigger="load" '
    'hx-swap="none"></span>')


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
