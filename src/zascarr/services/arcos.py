"""BL-C4 (#151): arcos/sagas en orden de lectura, aunque crucen series.

Solo lectura sobre `story_arcs` y `story_arc_issues.reading_order`. No crea ni
modifica arcos, no consulta fuentes y no toca archivos.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, Series, StoryArc, StoryArcIssue

POR_PAGINA = 50


@dataclass(frozen=True)
class ArcoResumen:
    id: str
    title: str
    is_crossover: bool
    numeros: int
    series: int


@dataclass(frozen=True)
class FilaArco:
    orden: int
    issue_id: str
    series_id: str
    series: str
    numero: str
    titulo: str | None
    fecha: str | None
    disponible: bool


@dataclass(frozen=True)
class PaginaArcos:
    filas: list[ArcoResumen]
    total: int
    pagina: int
    paginas: int
    desde: int
    hasta: int


@dataclass(frozen=True)
class DetalleArco:
    id: str
    title: str
    description: str | None
    is_crossover: bool
    filas: list[FilaArco]
    series: int


async def listar_arcos(db: AsyncSession, pagina: int = 1) -> PaginaArcos:
    total = (await db.execute(
        select(func.count()).select_from(StoryArc))).scalar_one()
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    desde = (pagina - 1) * POR_PAGINA
    filas = (await db.execute(
        select(
            StoryArc.id, StoryArc.title, StoryArc.is_crossover,
            func.count(StoryArcIssue.issue_id).label("numeros"),
            func.count(func.distinct(Issue.series_id)).label("series"),
        )
        .outerjoin(StoryArcIssue, StoryArcIssue.story_arc_id == StoryArc.id)
        .outerjoin(Issue, Issue.id == StoryArcIssue.issue_id)
        .group_by(StoryArc.id, StoryArc.title, StoryArc.is_crossover)
        .order_by(StoryArc.title, StoryArc.id)
        .offset(desde).limit(POR_PAGINA))).all()
    return PaginaArcos(
        filas=[ArcoResumen(str(f.id), f.title, bool(f.is_crossover),
                           int(f.numeros or 0), int(f.series or 0)) for f in filas],
        total=total, pagina=pagina, paginas=paginas, desde=desde,
        hasta=min(desde + POR_PAGINA, total))


async def detalle_arco(db: AsyncSession, arco_id: UUID) -> DetalleArco | None:
    arco = (await db.execute(
        select(StoryArc).where(StoryArc.id == arco_id))).scalar_one_or_none()
    if arco is None:
        return None
    filas = (await db.execute(
        select(
            StoryArcIssue.reading_order, Issue.id.label("issue_id"),
            Issue.issue_number, Issue.title.label("issue_title"),
            Issue.release_date, Series.id.label("series_id"),
            Series.title.label("series_title"),
            exists().where(File.issue_id == Issue.id,
                           File.is_missing.is_(False)).label("disponible"),
        )
        .join(Issue, Issue.id == StoryArcIssue.issue_id)
        .join(Series, Series.id == Issue.series_id)
        .where(StoryArcIssue.story_arc_id == arco_id)
        .order_by(StoryArcIssue.reading_order, Series.title, Issue.issue_number)
    )).all()
    detalle = [
        FilaArco(
            orden=int(f.reading_order), issue_id=str(f.issue_id),
            series_id=str(f.series_id), series=f.series_title,
            numero=f.issue_number or "Sin número", titulo=f.issue_title,
            fecha=f.release_date.isoformat() if f.release_date else None,
            disponible=bool(f.disponible))
        for f in filas
    ]
    return DetalleArco(
        id=str(arco.id), title=arco.title, description=arco.description,
        is_crossover=bool(arco.is_crossover), filas=detalle,
        series=len({f.series_id for f in detalle}))
