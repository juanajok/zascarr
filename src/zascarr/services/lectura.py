"""Marcar un número como pendiente/leyendo/leído y puntuarlo (#150 BL-C3).

Solo lectura de estado propia: no toca archivos, no consulta fuentes y no necesita migración.
`ReadingProgress` ya es 1:1 con `Issue` (`issue_id` único). El servicio valida todo y es
idempotente: repetir la misma marca no duplica filas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Issue, ReadingProgress, ReadingStatus
from zascarr.utils.texto_html import texto_plano

#: Solo los tres estados que expone este corte.
ESTADOS = (ReadingStatus.UNREAD, ReadingStatus.READING, ReadingStatus.COMPLETED)
ESTADO_ES = {
    ReadingStatus.UNREAD: "Sin leer",
    ReadingStatus.READING: "Leyendo",
    ReadingStatus.COMPLETED: "Leído",
}
MAX_NOTA = 280
MAX_RATING = 5
TEXTOS_LECTURA = {
    "titulo": "Tu lectura",
    "estado": "Estado de lectura",
    "valoracion": "Valoración",
    "nota": "Nota",
    "guardar": "Guardar lectura",
    "sin_valorar": "Sin valorar",
    "pendiente": "Sin leer", "leyendo": "Leyendo", "leido": "Leído",
    "ayuda": "Márcalo cuando lo termines; ZascArr no lee el archivo.",
    "garantia": "Quitar «Leído» borra la fecha de fin, pero conserva tu nota y tu puntuación.",
    "sin_guardar": "Todavía no has guardado nada de este número.",
    "guardando": "Guardando…", "guardado": "Guardado:",
    "max_nota": "Máximo 280 caracteres.",
    "puntuacion": "Puntuación (1–5)", "sin_puntuacion": "Sin puntuación",
    "nota_corta": "Nota corta", "guardar_mi_lectura": "Guardar mi lectura",
    "empezado": "Empezado", "terminado": "Terminado",
    "guardar_error": "No se ha guardado. Vuelve a intentarlo.",
    "leido_el": "Leído el", "empezado_el": "Empezado el",
}
#: Distingue «no lo he tocado» de «bórralo» en rating/nota.
_SIN_VALOR = object()


class IssueNoEncontradoError(LookupError):
    pass


class EstadoInvalidoError(ValueError):
    pass


class ValoracionInvalidaError(ValueError):
    pass


class NotaInvalidaError(ValueError):
    pass


@dataclass(frozen=True)
class EstadoLectura:
    issue_id: str
    estado: ReadingStatus
    rating: int | None
    nota: str | None
    started_at: datetime | None
    completed_at: datetime | None

    @property
    def estado_es(self) -> str:
        return ESTADO_ES[self.estado]


def _normalizar_nota(nota: str | None) -> str | None:
    if nota is None:
        return None
    limpio = texto_plano(nota)
    if len(limpio) > MAX_NOTA:
        raise NotaInvalidaError(f"La nota no puede pasar de {MAX_NOTA} caracteres.")
    return limpio or None


def _normalizar_rating(rating: int | str | None) -> int | None:
    if rating is None or rating == "":
        return None
    try:
        valor = int(rating)
    except (TypeError, ValueError):
        raise ValoracionInvalidaError("La valoración tiene que ser un número del 1 al 5.") from None
    if not 1 <= valor <= MAX_RATING:
        raise ValoracionInvalidaError("La valoración tiene que estar entre 1 y 5.")
    return valor


def _normalizar_estado(estado: str | ReadingStatus) -> ReadingStatus:
    try:
        valor = estado if isinstance(estado, ReadingStatus) else ReadingStatus(str(estado))
    except ValueError:
        raise EstadoInvalidoError("Ese estado de lectura no existe.") from None
    if valor not in ESTADOS:
        raise EstadoInvalidoError("Ese estado de lectura no se puede marcar aquí.")
    return valor


def _instantanea(p: ReadingProgress) -> EstadoLectura:
    return EstadoLectura(str(p.issue_id), p.status, p.rating, p.notes, p.started_at, p.completed_at)


async def marcar(
    db: AsyncSession,
    issue_id: UUID,
    estado: str | ReadingStatus,
    *,
    rating: int | str | None | object = _SIN_VALOR,
    nota: str | None | object = _SIN_VALOR,
    series_id: UUID | None = None,
) -> EstadoLectura:
    """Marca un número; valida y conserva rating/nota al desmarcar «leído»."""
    nuevo_estado = _normalizar_estado(estado)
    nuevo_rating = _normalizar_rating(rating) if rating is not _SIN_VALOR else _SIN_VALOR
    nueva_nota = _normalizar_nota(nota) if nota is not _SIN_VALOR else _SIN_VALOR
    consulta = select(Issue.id).where(Issue.id == issue_id)
    if series_id is not None:
        consulta = consulta.where(Issue.series_id == series_id)
    issue = (await db.execute(consulta)).scalar_one_or_none()
    if issue is None:
        raise IssueNoEncontradoError("Ese número no está en tu biblioteca.")
    progreso = (
        await db.execute(select(ReadingProgress).where(ReadingProgress.issue_id == issue_id))
    ).scalar_one_or_none()
    ahora = datetime.now(UTC)
    if progreso is None:
        progreso = ReadingProgress(issue_id=issue_id, status=nuevo_estado)
        db.add(progreso)
    anterior = progreso.status
    progreso.status = nuevo_estado
    if nuevo_rating is not _SIN_VALOR:
        progreso.rating = nuevo_rating
    elif progreso.rating is None:
        progreso.rating = None
    if nueva_nota is not _SIN_VALOR:
        progreso.notes = nueva_nota
    if (
        nuevo_estado in (ReadingStatus.READING, ReadingStatus.COMPLETED)
        and progreso.started_at is None
    ):
        progreso.started_at = ahora
    if nuevo_estado is ReadingStatus.COMPLETED:
        if progreso.completed_at is None:
            progreso.completed_at = ahora
    elif anterior is ReadingStatus.COMPLETED:
        progreso.completed_at = None
    await db.flush()
    await db.commit()
    return _instantanea(progreso)


async def lectura_de(db: AsyncSession, issue_id: UUID) -> EstadoLectura | None:
    p = (
        await db.execute(select(ReadingProgress).where(ReadingProgress.issue_id == issue_id))
    ).scalar_one_or_none()
    return None if p is None else _instantanea(p)


async def lecturas_de_serie(db: AsyncSession, series_id: UUID) -> dict[str, EstadoLectura]:
    """Una consulta fija para todas las filas de lectura de la serie."""
    filas = (
        (
            await db.execute(
                select(ReadingProgress)
                .join(Issue, Issue.id == ReadingProgress.issue_id)
                .where(Issue.series_id == series_id)
            )
        )
        .scalars()
        .all()
    )
    return {str(p.issue_id): _instantanea(p) for p in filas}


async def recuento_lectura(
        db: AsyncSession, series_ids: list[UUID], modo: str = "si") -> str | None:
    """Recuento por SERIES (no por números) para el filtro de lectura."""
    if not series_ids:
        return "0 de 0 series."
    from zascarr.models import ReadingStatus
    total = len(set(series_ids))
    if modo == "leyendo":
        estado = ReadingStatus.READING
        n = (await db.execute(select(func.count(func.distinct(Issue.series_id)))
                              .join(ReadingProgress, ReadingProgress.issue_id == Issue.id)
                              .where(Issue.series_id.in_(series_ids),
                                     ReadingProgress.status == estado))).scalar_one()
        return f"{n} de {total} series con algún número en lectura."
    if modo == "no":
        con_leido = (await db.execute(select(func.count(func.distinct(Issue.series_id)))
                                      .join(ReadingProgress, ReadingProgress.issue_id == Issue.id)
                                      .where(Issue.series_id.in_(series_ids),
                                             ReadingProgress.status == ReadingStatus.COMPLETED)
                                      )).scalar_one()
        return f"{total - con_leido} de {total} series sin ningún número leído."
    n = (await db.execute(select(func.count(func.distinct(Issue.series_id)))
                          .join(ReadingProgress, ReadingProgress.issue_id == Issue.id)
                          .where(Issue.series_id.in_(series_ids),
                                 ReadingProgress.status == ReadingStatus.COMPLETED))).scalar_one()
    return f"{n} de {total} series con algún número leído."
