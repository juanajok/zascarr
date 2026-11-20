"""
Blindaje legal — LEGAL.md, aceptación y la dependencia que la exige.

Solo gatea lo que de verdad dispara red/descarga hacia fuentes externas
de contenido: crear/reintentar un item de wishlist y el ciclo del
orquestador (ver orchestrator.py). Biblioteca, pendientes y fichas de
serie NO llevan este gate — el riesgo legal real es "facilitar
descargas", no "ver tu propia biblioteca ya organizada" (ver LEGAL.md).

Sin modelo de usuario (herramienta de un solo operador): el estado de
aceptación es único para todo el sistema, no por persona.

legal_version no es una constante que haya que recordar subir a mano
cada vez que cambie LEGAL.md — es el hash del propio fichero. Editar
LEGAL.md invalida automáticamente cualquier aceptación anterior.
"""
from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlsplit

import markdown
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.database import get_db
from zascarr.models import LegalAcknowledgment

LEGAL_MD_PATH = Path(__file__).parent.parent / "LEGAL.md"


@lru_cache
def _legal_md_text() -> str:
    return LEGAL_MD_PATH.read_text(encoding="utf-8")


@lru_cache
def current_legal_version() -> str:
    """Hash del LEGAL.md empaquetado con la app — cambia solo si el
    fichero cambia, nunca hay que sincronizarlo a mano con una
    constante. Cacheado: el fichero no cambia sin reiniciar el proceso."""
    return hashlib.sha256(_legal_md_text().encode("utf-8")).hexdigest()[:16]


def render_legal_html() -> str:
    return markdown.markdown(_legal_md_text(), extensions=["tables"])


async def get_acknowledgment(db: AsyncSession) -> LegalAcknowledgment | None:
    return (await db.execute(
        select(LegalAcknowledgment)
        .where(LegalAcknowledgment.legal_version == current_legal_version())
        .order_by(LegalAcknowledgment.accepted_at.desc())
        .limit(1)
    )).scalar_one_or_none()


async def is_acknowledged(db: AsyncSession) -> bool:
    return await get_acknowledgment(db) is not None


async def acknowledge(db: AsyncSession) -> LegalAcknowledgment:
    ack = LegalAcknowledgment(
        accepted_at=datetime.now(UTC),
        legal_version=current_legal_version(),
    )
    db.add(ack)
    await db.flush()
    return ack


RETORNO_LEGAL_POR_DEFECTO = "/ui/biblioteca"
_MAX_RETORNO_LEGAL = 2000


def volver_legal(valor: str | None) -> str:
    """Destino interno seguro para volver tras aceptar el aviso.

    Solo rutas locales de la propia UI. Rechaza esquemas, hosts, ``//``,
    retrocesos de ruta, controles y el propio aviso legal. La validación se
    repite al confirmar: el campo oculto no es una autoridad.
    """
    if not valor or len(valor) > _MAX_RETORNO_LEGAL:
        return RETORNO_LEGAL_POR_DEFECTO
    if any(ord(c) < 32 or ord(c) == 127 or c == "\\" for c in valor):
        return RETORNO_LEGAL_POR_DEFECTO
    try:
        partes = urlsplit(valor)
    except ValueError:
        return RETORNO_LEGAL_POR_DEFECTO
    if partes.scheme or partes.netloc or not partes.path.startswith("/ui/"):
        return RETORNO_LEGAL_POR_DEFECTO
    if partes.path == "/ui/legal" or partes.path.startswith("/ui/legal/"):
        return RETORNO_LEGAL_POR_DEFECTO
    if ".." in partes.path.split("/"):
        return RETORNO_LEGAL_POR_DEFECTO
    return valor


def _destino_de_la_peticion(request: Request | None) -> str:
    """La página desde la que se intentó la acción, si es una ruta UI válida."""
    if request is None:
        return RETORNO_LEGAL_POR_DEFECTO
    candidatos = (
        request.headers.get("hx-current-url"),
        request.headers.get("referer"),
        (f"{request.url.path}?{request.url.query}" if request.url.query else request.url.path)
        if request.method == "GET" else None,
    )
    for candidato in candidatos:
        if not candidato:
            continue
        # Referer llega como URL absoluta: se conserva solo su parte local.
        try:
            partes = urlsplit(candidato)
        except ValueError:
            continue
        if partes.scheme or partes.netloc:
            candidato = partes.path + (f"?{partes.query}" if partes.query else "")
        destino = volver_legal(candidato)
        if destino != RETORNO_LEGAL_POR_DEFECTO:
            return destino
    return RETORNO_LEGAL_POR_DEFECTO


async def require_legal_acknowledgment(
    request: Request, db: AsyncSession = Depends(get_db)
) -> None:
    """Dependencia de FastAPI — aplicar SOLO a rutas que disparen
    búsqueda/descarga (crear o reintentar un item de wishlist). El 403
    lleva HX-Redirect: si la petición vino de HTMX (hx-post/hx-get),
    htmx navega solo a /ui/legal — mecanismo nativo, cero JS nuevo. Un
    cliente JSON puro recibe el mismo 403 con el mismo `detail`."""
    if not await is_acknowledged(db):
        destino = _destino_de_la_peticion(request)
        url = "/ui/legal"
        if destino != RETORNO_LEGAL_POR_DEFECTO:
            url += f"?volver={quote(destino, safe='')}"
        raise HTTPException(
            status_code=403,
            detail="legal_acknowledgment_required",
            headers={"HX-Redirect": url},
        )
