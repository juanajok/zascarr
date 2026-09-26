"""
Router de la lista de deseos (D1) — /ui/wishlist.

Buscar una serie ya existente en la biblioteca y marcarla como deseada;
el ciclo de fondo (`_orchestrator_loop`, ver main.py) se encarga de
buscarla, descargarla e importarla solo. Esta pantalla solo refleja el
estado (`Wishlist.status`) — la lógica de negocio vive en WishlistService,
no aquí, mismo patrón que pendientes.py/ReviewService (B2).
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.models import Issue, Wishlist, WishlistStatus
from zascarr.services.legal import is_acknowledged, require_legal_acknowledgment
from zascarr.services.orchestrator import (
    Orchestrator,
    crear_token_candidato,
    verificar_token_candidato,
)
from zascarr.services.wishlist import WishlistService
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/wishlist", tags=["ui"])

_ESTADO_LABEL = {
    WishlistStatus.WANTED: "Buscando…",
    WishlistStatus.SEARCHING: "Buscando…",
    WishlistStatus.DOWNLOADING: "Descargando…",
    WishlistStatus.DOWNLOADED: "Descargando…",
    WishlistStatus.IMPORTED: "En tu biblioteca",
    WishlistStatus.FAILED: "Sin resultados",
}

# Carga anticipada de las relaciones que _row() necesita, para no disparar
# lazy-load asíncrono (MissingGreenlet) al leer item.series/item.issue.series
# fuera de una llamada await explícita — mismo cuidado que enricher.py
# documenta para issue.credits.
_EAGER = (selectinload(Wishlist.series), selectinload(Wishlist.issue).selectinload(Issue.series))


def _row(item: Wishlist) -> dict:
    series = item.series or (item.issue.series if item.issue else None)
    titulo = series.title if series else "?"
    if item.issue and item.issue.issue_number:
        titulo = f"{titulo} #{item.issue.issue_number}"
    return {
        "item": item,
        "titulo": titulo,
        "estado": _ESTADO_LABEL.get(item.status, item.status.value),
        "puede_reintentar": item.status == WishlistStatus.FAILED,
        # D10: "Buscar ahora" solo tiene sentido en un estado accionable —
        # una vez descargando/en biblioteca, esto no es la herramienta
        # para tocarlo (no hay override manual de una descarga en curso).
        "puede_buscar_ahora": item.status in (WishlistStatus.WANTED, WishlistStatus.FAILED),
        # D9: motivo concreto de por qué esta fila no avanza (o avanzó
        # y ya no aplica) — escrito por el orquestador, nunca inventado
        # aquí. "Sin resultados" en el badge de estado ya no es lo único
        # que ve el coleccionista cuando algo se estanca.
        "motivo": item.last_error,
    }


async def _get_row(db: AsyncSession, item_id) -> dict:
    item = (await db.execute(
        select(Wishlist).options(*_EAGER).where(Wishlist.id == item_id)
    )).scalar_one()
    return _row(item)


@router.get("", response_class=HTMLResponse)
async def index(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    items = list((await db.execute(
        select(Wishlist).options(*_EAGER).order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
    )).scalars().all())
    rows = [_row(item) for item in items]
    # D9: el aviso legal pendiente es un estado GLOBAL del sistema (no de
    # una fila concreta) — se muestra como banner aparte, no se escribe
    # en Wishlist.last_error de cada item (ver services/orchestrator.py).
    aviso_legal_pendiente = not await is_acknowledged(db)
    return templates.TemplateResponse(
        request, "wishlist.html", {"rows": rows, "aviso_legal_pendiente": aviso_legal_pendiente}
    )


@router.get("/buscar-serie", response_class=HTMLResponse)
async def buscar_serie(request: Request, q: str = "", db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    series_list = await WishlistService(db).search_series(q)
    return templates.TemplateResponse(
        request, "_resultados_series_wishlist.html", {"series_list": series_list}
    )


@router.post("/anadir", response_class=HTMLResponse, dependencies=[Depends(require_legal_acknowledgment)])
async def anadir(request: Request, series_id: UUID = Form(...), db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        item = await WishlistService(db).add(series_id=series_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await _get_row(db, item.id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})


@router.post("/{item_id}/quitar", response_class=HTMLResponse)
async def quitar(item_id: UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await WishlistService(db).remove(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse("")


@router.post("/{item_id}/reintentar", response_class=HTMLResponse, dependencies=[Depends(require_legal_acknowledgment)])
async def reintentar(item_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await WishlistService(db).retry(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    row = await _get_row(db, item_id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})


# ── D10: búsqueda manual con confirmación explícita ──────────────────────────
# "Buscar ahora" muestra los candidatos reales (fuente/tamaño/formato) SIN
# tocar Transmission/aMule; solo al confirmar UNO concreto se envía.
#
# Hallazgo de revisión (2026-09-26): la primera versión reenviaba los
# campos del candidato en claro (título, download_url...) en campos
# ocultos, y el servidor los recogía sin comprobar que vinieran de verdad
# de una búsqueda hecha para este item — un formulario manipulado podía
# colar cualquier URL. Ahora el formulario solo reenvía un token firmado
# por el servidor (crear_token_candidato/verificar_token_candidato,
# services/orchestrator.py) que liga el candidato al item_id y caduca a
# los 10 minutos; los datos nunca vuelven a viajar sueltos.

def _formato_de(titulo: str) -> str:
    t = titulo.lower()
    if ".cbz" in t:
        return "CBZ"
    if ".cbr" in t:
        return "CBR"
    return "?"


@router.post("/{item_id}/buscar-ahora", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def buscar_ahora(item_id: UUID, request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    item = await db.get(Wishlist, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    resultado = await Orchestrator(db).preview_candidates(item)
    no_se_pudo_buscar = resultado is None
    sin_candidatos = resultado is not None and not resultado
    secret = get_settings().secret_key
    filas = [
        {
            "c": c,
            "formato": _formato_de(c.title),
            "token": crear_token_candidato(item_id, c, secret),
        }
        for c in (resultado or [])
    ]
    return templates.TemplateResponse(request, "_candidatos_wishlist.html", {
        "item_id": item_id,
        "candidatos": filas,
        "no_se_pudo_buscar": no_se_pudo_buscar,
        "sin_candidatos": sin_candidatos,
        "motivo": item.last_error if sin_candidatos else None,
    })


@router.post("/{item_id}/cancelar-busqueda", response_class=HTMLResponse)
async def cancelar_busqueda(item_id: UUID) -> HTMLResponse:
    """D10: cancelar no deja nada a medias — no se tocó Transmission/aMule
    al listar candidatos, así que "cancelar" es solo cerrar el panel."""
    return HTMLResponse("")


@router.post("/{item_id}/enviar-candidato", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def enviar_candidato(
    item_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
    token: str = Form(...),
) -> HTMLResponse:
    item = await db.get(Wishlist, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item no encontrado")
    candidato = verificar_token_candidato(token, item_id, get_settings().secret_key)
    if candidato is None:
        # Token inválido, de otro item, manipulado o caducado — nunca se
        # reconstruye el candidato a partir de datos sueltos del formulario.
        raise HTTPException(
            status_code=400, detail="Candidato no válido o caducado — vuelve a buscar"
        )
    await Orchestrator(db).send_manual_candidate(item, candidato)
    row = await _get_row(db, item_id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})
