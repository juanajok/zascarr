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
from zascarr.services.estado_deseo import aspecto_de_deseo
from zascarr.services.legal import is_acknowledged, require_legal_acknowledgment
from zascarr.services.orchestrator import (
    Orchestrator,
    crear_token_candidato,
    prowlarr_configurado,
    verificar_token_candidato,
)
from zascarr.services.transmission import TransmissionClient
from zascarr.services.wishlist import WishlistService
from zascarr.web.retorno import url_de_ficha_desde_deseos
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(prefix="/ui/wishlist", tags=["ui"])

_ESTADO_LABEL = {
    # «Buscando…» solo mientras se busca de verdad: un deseo que espera al ciclo (o al aviso legal,
    # que pausa las búsquedas) decía «Buscando…» bajo «búsquedas en pausa» (caso real, 2026-10-20).
    WishlistStatus.WANTED: "Por buscar",
    WishlistStatus.SEARCHING: "Buscando…",
    WishlistStatus.DOWNLOADING: "Descargando…",
    WishlistStatus.DOWNLOADED: "Descargado",  # terminó; espera al importador
    WishlistStatus.IMPORTED: "En tu biblioteca",
    WishlistStatus.FAILED: "Sin resultados",
    # D8: lo retiró la política (dejó de querer ese número), no falló nada. Se
    # etiqueta explícitamente en vez de dejar el valor crudo del enum.
    WishlistStatus.RETIRADO: "Retirado",
}

# Carga anticipada de las relaciones que _row() necesita, para no disparar
# lazy-load asíncrono (MissingGreenlet) al leer item.series/item.issue.series
# fuera de una llamada await explícita — mismo cuidado que enricher.py
# documenta para issue.credits.
_EAGER = (selectinload(Wishlist.series), selectinload(Wishlist.issue).selectinload(Issue.series))


def _row(item: Wishlist) -> dict:
    series = item.series or (item.issue.series if item.issue else None)
    referencia = ((getattr(series, "reference_name", None) or series.title)
                  if series else "?")
    if item.issue:
        numero = item.issue.number_key or item.issue.issue_number
        if numero:
            referencia = f"{referencia} #{numero}"
    return {
        "item": item,
        "referencia": referencia,
        "enlace_ficha": (url_de_ficha_desde_deseos(series.id)
                         if series is not None else None),
        "estado": _ESTADO_LABEL.get(item.status, item.status.value),
        "aspecto": aspecto_de_deseo(item.status),      # aspecto de `ui.chip`, no una clase CSS
        "puede_reintentar": item.status == WishlistStatus.FAILED,
        # D10: "Buscar ahora" solo tiene sentido en un estado accionable —
        # una vez descargando/en biblioteca, esto no es la herramienta
        # para tocarlo (no hay override manual de una descarga en curso).
        "puede_buscar_ahora": item.status in (WishlistStatus.WANTED, WishlistStatus.FAILED),
        # Descargas manuales que no enlazan (p. ej. _Unsorted → especial): se
        # pueden dar por conseguidas a mano para no dejar el deseo colgado.
        "puede_marcar_conseguido": item.status == WishlistStatus.DOWNLOADING,
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
        select(Wishlist)
        # D8: los items que la política retiró no son deseos activos, pero
        # tampoco se borran (dejan constancia). Se ocultan de la lista para que
        # pasar una serie larga a «ninguno» no llene la pantalla de filas
        # retiradas; siguen en la BD y en la API (`?status=retirado`).
        .where(Wishlist.status != WishlistStatus.RETIRADO)
        .options(*_EAGER)
        .order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
    )).scalars().all())
    rows = [_row(item) for item in items]
    # D9: el aviso legal pendiente es un estado GLOBAL del sistema (no de
    # una fila concreta) — se muestra como banner aparte, no se escribe
    # en Wishlist.last_error de cada item (ver services/orchestrator.py).
    aviso_legal_pendiente = not await is_acknowledged(db)
    settings = get_settings()
    prowlarr_incompleto = bool(
        getattr(settings, "prowlarr_enabled", False) and not prowlarr_configurado(settings))
    en_descarga = sum(
        1 for r in rows
        if r["item"].status in (WishlistStatus.DOWNLOADING, WishlistStatus.DOWNLOADED))
    return templates.TemplateResponse(
        request, "wishlist.html", {
            "rows": rows,
            "total": len(rows),
            "en_descarga": en_descarga,
            "aviso_legal_pendiente": aviso_legal_pendiente,
            "prowlarr_incompleto": prowlarr_incompleto,
        }
    )


@router.get("/buscar-serie", response_class=HTMLResponse)
async def buscar_serie(
    request: Request, q: str = "", db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    series_list = await WishlistService(db).search_series(q)
    return templates.TemplateResponse(
        request, "_resultados_series_wishlist.html", {"series_list": series_list}
    )


@router.post(
    "/anadir", response_class=HTMLResponse, dependencies=[Depends(require_legal_acknowledgment)]
)
async def anadir(
    request: Request, series_id: UUID = Form(...), db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
    try:
        item = await WishlistService(db).add(series_id=series_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    row = await _get_row(db, item.id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})


@router.get("/progreso", response_class=HTMLResponse)
async def progreso(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Cola/progreso de los deseos en descarga (hueco del benchmark 2026-11-16).

    Una sola consulta a Transmission por refresco (no una por fila); aMule no
    expone progreso por su web, así que se indica como tal. Solo incluye deseos
    en DOWNLOADING/DOWNLOADED: el resto de la pantalla no se duplica.
    """
    items = list((await db.execute(
        select(Wishlist)
        .where(Wishlist.status.in_([WishlistStatus.DOWNLOADING,
                                    WishlistStatus.DOWNLOADED]))
        .options(*_EAGER)
        .order_by(Wishlist.added_at.asc())
    )).scalars().all())
    if not items:
        return HTMLResponse("")

    settings = get_settings()
    torrents: dict[str, dict] = {}
    hay_transmission = any(
        (i.download_backend or "") == "transmission" and i.download_ref for i in items)
    if hay_transmission and getattr(settings, "transmission_enabled", False):
        try:
            torrents = {
                str(t.get("hashString", "")).lower(): t
                for t in await TransmissionClient().list_torrents()
                if t.get("hashString")
            }
        except Exception:
            # Sin acceso al cliente se sigue mostrando el deseo como «en cola».
            torrents = {}

    filas = []
    for item in items:
        row = _row(item)
        backend = (item.download_backend or "").lower()
        pct: int | None = None
        detalle = "En cola de descarga"
        if backend == "transmission" and item.download_ref:
            torrent = torrents.get(str(item.download_ref).lower())
            if torrent is not None:
                pct = round(float(torrent.get("percentDone") or 0) * 100)
                detalle = "Completado, pendiente de importar" if pct >= 100 else "Transmission"
            else:
                detalle = "Transmission (no está en la lista del cliente)"
        elif backend == "amule":
            detalle = "aMule (sin progreso por aquí)"
        filas.append({
            "item_id": item.id,
            "referencia": row["referencia"],
            "backend": backend,
            "pct": pct,
            "detalle": detalle,
        })
    return templates.TemplateResponse(
        request, "_progreso_wishlist.html", {"filas": filas})


@router.post("/{item_id}/marcar-conseguido", response_class=HTMLResponse)
async def marcar_conseguido(item_id: UUID, request: Request,
                            db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    """Cierra un deseo que ya está en la biblioteca aunque el importador no lo
    haya ligado (p. ej. quedó en _Unsorted y luego se guardó como especial)."""
    try:
        await WishlistService(db).marcar_conseguido(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    row = await _get_row(db, item_id)
    return templates.TemplateResponse(request, "_fila_wishlist.html", {"row": row})


@router.post("/{item_id}/quitar", response_class=HTMLResponse)
async def quitar(item_id: UUID, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    try:
        await WishlistService(db).remove(item_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return HTMLResponse("")


@router.post(
    "/{item_id}/reintentar",
    response_class=HTMLResponse,
    dependencies=[Depends(require_legal_acknowledgment)],
)
async def reintentar(
    item_id: UUID, request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
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
async def buscar_ahora(
    item_id: UUID, request: Request, db: AsyncSession = Depends(get_db)
) -> HTMLResponse:
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
        # No usar `_row()` aquí: `item` viene de `db.get` SIN las relaciones
        # precargadas y acceder a `item.series` en async lanza MissingGreenlet
        # (500 real 2026-11-17). Para la etiqueta basta la consulta guardada.
        "item_titulo": (item.search_query or "").strip() if item else "",
        "candidatos": filas,
        "no_se_pudo_buscar": no_se_pudo_buscar,
        "sin_candidatos": sin_candidatos,
        "motivo": item.last_error if sin_candidatos else None,
    })


#: Tope de deseos por tanda: cada búsqueda puede tardar hasta ~2 min (foro/cortesía).
MAX_LOTE = 8


def _resultado_lote(request: Request, mensaje: str, parciales: list[str]):
    """Aviso de la tanda + parciales de candidatos en OOB (sin tocar el estado del deseo)."""
    return templates.TemplateResponse(request, "_resultado_lote.html", {
        "mensaje": mensaje,
        "parciales": "".join(parciales),
    })


@router.post("/buscar-lote", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def buscar_lote(
    request: Request,
    item_id: list[UUID] = Form(default=[]),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Busca varios deseos en secuencia y devuelve cada panel de candidatos en OOB.

    No usa `_row()`: los items vienen de `db.get` sin relaciones precargadas y tocar
    `item.series`/`item.issue` lanzaría MissingGreenlet (regresión 2026-11-17). El panel se
    renderiza con `templates.env.get_template(...).render(...)` para poder incrustarlo en la
    respuesta OOB conservando el mismo parcial que «Buscar ahora». No cambia el estado del
    deseo ni envía nada a los clientes de descarga.
    """
    ids = list(dict.fromkeys(item_id))
    if not ids:
        return _resultado_lote(request, "No has seleccionado ningún deseo.", [])
    if len(ids) > MAX_LOTE:
        return _resultado_lote(
            request,
            f"Has seleccionado {len(ids)} deseos; el máximo por tanda es {MAX_LOTE}. "
            "Marca menos y vuelve a intentarlo.", [])
    orquestador = Orchestrator(db)
    secret = get_settings().secret_key
    parciales: list[str] = []
    buscados = 0
    saltados = 0
    plantilla = templates.env.get_template("_candidatos_wishlist.html")
    for ident in ids:
        item = await db.get(Wishlist, ident)
        if item is None:
            saltados += 1
            continue
        resultado = await orquestador.preview_candidates(item)
        filas = [
            {"c": candidato, "formato": _formato_de(candidato.title),
             "token": crear_token_candidato(ident, candidato, secret)}
            for candidato in (resultado or [])
        ]
        parcial = plantilla.render(
            item_id=ident,
            item_titulo=(item.search_query or "").strip(),
            candidatos=filas,
            no_se_pudo_buscar=resultado is None,
            sin_candidatos=resultado is not None and not resultado,
            motivo=item.last_error if resultado is not None and not resultado else None,
        )
        # El root del parcial ya tiene el id vivo: se le añade el swap OOB para que htmx
        # sustituya ESE panel y no todo el contenedor del lote.
        parcial = parcial.replace(
            f'<div class="candidatos-wishlist" id="candidatos-{ident}">',
            f'<div class="candidatos-wishlist" id="candidatos-{ident}" '
            f'hx-swap-oob="outerHTML:#candidatos-{ident}">', 1)
        parciales.append(parcial)
        buscados += 1
    mensaje = (f"Se buscaron {buscados} deseo{'s' if buscados != 1 else ''}; "
               "cada resultado está en su fila.")
    if saltados:
        mensaje += f" {saltados} ya no estaban en la lista."
    return _resultado_lote(request, mensaje, parciales)


@router.post("/{item_id}/cancelar-busqueda", response_class=HTMLResponse)
async def cancelar_busqueda(item_id: UUID) -> HTMLResponse:
    """D10: cancelar no deja nada a medias — no se tocó Transmission/aMule
    al listar candidatos, así que "cancelar" es solo cerrar el panel."""
    return HTMLResponse("")


@router.post("/{item_id}/enviar-candidato", response_class=HTMLResponse,
             dependencies=[Depends(require_legal_acknowledgment)])
async def enviar_candidato(
    item_id: UUID, request: Request, db: AsyncSession = Depends(get_db),
    token: str = Form(...), indice: int = Form(0),
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
    exito = await Orchestrator(db).send_manual_candidate(item, candidato)
    # Se actualiza SOLO el estado de la fila (OOB) y el candidato pulsado: el resto de
    # candidatos del preview sigue visible para enviar varios sin repetir la búsqueda.
    row = await _get_row(db, item_id)
    return templates.TemplateResponse(request, "_candidato_enviado.html", {
        "row": row,
        "item_id": item_id,
        "indice": indice,
        "titulo": candidato.title,
        "token": token,
        "exito": exito,
    })
