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

import markdown
from fastapi import Depends, HTTPException
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


async def require_legal_acknowledgment(db: AsyncSession = Depends(get_db)) -> None:
    """Dependencia de FastAPI — aplicar SOLO a rutas que disparen
    búsqueda/descarga (crear o reintentar un item de wishlist). El 403
    lleva HX-Redirect: si la petición vino de HTMX (hx-post/hx-get),
    htmx navega solo a /ui/legal — mecanismo nativo, cero JS nuevo. Un
    cliente JSON puro recibe el mismo 403 con el mismo `detail`."""
    if not await is_acknowledged(db):
        raise HTTPException(
            status_code=403,
            detail="legal_acknowledgment_required",
            headers={"HX-Redirect": "/ui/legal"},
        )
