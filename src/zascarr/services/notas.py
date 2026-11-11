# ruff: noqa: E501
"""BL-WK4 (#342): notas libres de colección por serie o por número.

No reutiliza `ReadingProgress.notes` (lectura) ni `Wishlist.notes` (deseo): una
nota de colección es texto de la persona sobre una serie o un número. Solo se
guarda texto plano; la plantilla se encarga del autoescape.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Issue, Note, Series

MAX_TEXTO = 4000


class NotaInvalidaError(ValueError):
    """Texto vacío o demasiado largo."""


def normalizar_texto(texto: str | None) -> str:
    """Quita espacios de los extremos y valida; conserva saltos de línea internos."""
    limpio = (texto or "").strip()
    if not limpio:
        raise NotaInvalidaError("La nota no puede estar vacía.")
    if len(limpio) > MAX_TEXTO:
        raise NotaInvalidaError(
            f"La nota es demasiado larga (máximo {MAX_TEXTO} caracteres).")
    return limpio


async def leer_serie(db: AsyncSession, series_id: UUID) -> Note | None:
    return (await db.execute(
        select(Note).where(Note.series_id == series_id)
    )).scalar_one_or_none()


async def leer_numero(db: AsyncSession, issue_id: UUID) -> Note | None:
    return (await db.execute(
        select(Note).where(Note.issue_id == issue_id)
    )).scalar_one_or_none()


async def guardar_serie(db: AsyncSession, series_id: UUID, texto: str | None) -> Note:
    limpio = normalizar_texto(texto)
    nota = await leer_serie(db, series_id)
    if nota is None:
        nota = Note(series_id=series_id, texto=limpio)
        db.add(nota)
    else:
        nota.texto = limpio
    await db.flush()
    return nota


async def guardar_numero(db: AsyncSession, issue_id: UUID, texto: str | None) -> Note:
    limpio = normalizar_texto(texto)
    nota = await leer_numero(db, issue_id)
    if nota is None:
        nota = Note(issue_id=issue_id, texto=limpio)
        db.add(nota)
    else:
        nota.texto = limpio
    await db.flush()
    return nota


async def borrar_serie(db: AsyncSession, series_id: UUID) -> bool:
    resultado = await db.execute(delete(Note).where(Note.series_id == series_id))
    await db.flush()
    return bool(resultado.rowcount)


async def borrar_numero(db: AsyncSession, issue_id: UUID) -> bool:
    resultado = await db.execute(delete(Note).where(Note.issue_id == issue_id))
    await db.flush()
    return bool(resultado.rowcount)


async def notas_de_serie(
    db: AsyncSession, series_id: UUID,
) -> tuple[Note | None, list[tuple[Note, Issue]]]:
    """Nota de la serie y notas de sus números, ordenadas por número."""
    serie = await leer_serie(db, series_id)
    filas = (await db.execute(
        select(Note, Issue)
        .join(Issue, Note.issue_id == Issue.id)
        .where(Issue.series_id == series_id)
        .order_by(Issue.sort_order.asc().nulls_last(), Issue.issue_number.asc().nulls_last())
    )).all()
    return serie, [(nota, issue) for nota, issue in filas]


async def serie_existe(db: AsyncSession, series_id: UUID) -> bool:
    return (await db.execute(
        select(Series.id).where(Series.id == series_id))).scalar_one_or_none() is not None


async def numero_existe(db: AsyncSession, series_id: UUID, issue_id: UUID) -> bool:
    return (await db.execute(
        select(Issue.id).where(Issue.id == issue_id, Issue.series_id == series_id)
    )).scalar_one_or_none() is not None
