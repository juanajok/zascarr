"""#1088: consultas acotadas de actividad de lectura, visitas y novedades.

Solo lectura. Cada carrusel resuelve su información en una consulta (o CTE),
sin N+1 y con `LIMIT` explícito. Las series vacías (sin archivos locales) no
entran en los carruseles.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.importer_triage import natural_key
from zascarr.models import File, Issue, ReadingProgress, ReadingStatus, Series

_NUMERO_SECUENCIAL = re.compile(r"^\d+(?:[.,]\d+)?$")


@dataclass(frozen=True)
class ContinuarLeyendo:
    series_id: str
    series_title: str
    issue_id: str
    numero: str
    titulo: str | None
    pagina: int
    total_paginas: int | None


@dataclass(frozen=True)
class UltimoLeido:
    series_id: str
    series_title: str
    last_read_at: datetime


@dataclass(frozen=True)
class PorEmpezar:
    series_id: str
    series_title: str
    total_numeros: int


@dataclass(frozen=True)
class RecienIncorporado:
    series_id: str
    series_title: str
    issue_id: str | None
    numero: str | None
    imported_at: datetime
    tipo: str  # "serie_nueva" | "numero_nuevo"


def _es_secuencial(numero: str | None) -> bool:
    return bool(numero and _NUMERO_SECUENCIAL.match(numero))


async def continuar_leyendo(db: AsyncSession, limite: int = 6) -> list[ContinuarLeyendo]:
    """Números en curso o el siguiente tras el último leído, con archivo local."""
    filas = (await db.execute(
        select(Issue.series_id, Series.title, Issue.id, Issue.issue_number,
               Issue.title.label("issue_title"), Issue.sort_order, Issue.page_count,
               ReadingProgress.status, ReadingProgress.current_page)
        .join(Series, Series.id == Issue.series_id)
        .outerjoin(ReadingProgress, ReadingProgress.issue_id == Issue.id)
        .where(Issue.id.in_(select(File.issue_id).where(
            File.issue_id.is_not(None), File.is_missing.is_(False))))
        .where(Issue.series_id.in_(select(Issue.series_id).join(
            ReadingProgress, ReadingProgress.issue_id == Issue.id).where(
                ReadingProgress.status.in_([ReadingStatus.READING, ReadingStatus.COMPLETED]))))
    )).all()
    por_serie: dict[str, list] = {}
    for fila in filas:
        por_serie.setdefault(str(fila.series_id), []).append(fila)
    resultado: list[ContinuarLeyendo] = []
    for serie_id, issues in por_serie.items():
        issues.sort(key=lambda f: (f.sort_order is None, f.sort_order or 0.0,
                                   natural_key(f.issue_number or "")))
        elegido = next((f for f in issues if f.status is ReadingStatus.READING), None)
        if elegido is None:
            leidos = [i for i, f in enumerate(issues) if f.status is ReadingStatus.COMPLETED]
            if not leidos:
                continue
            for f in issues[leidos[-1] + 1:]:
                if _es_secuencial(f.issue_number):
                    elegido = f
                    break
        if elegido is None or not _es_secuencial(elegido.issue_number):
            continue
        resultado.append(ContinuarLeyendo(
            serie_id, elegido.title, str(elegido.id), elegido.issue_number or "",
            elegido.issue_title, int(elegido.current_page or 0), elegido.page_count))
        if len(resultado) >= limite:
            break
    return resultado


async def ultimos_leidos(db: AsyncSession, limite: int = 6) -> list[UltimoLeido]:
    """MAX(last_read_at) por serie, sin duplicar filas."""
    filas = (await db.execute(
        select(Issue.series_id, Series.title, func.max(ReadingProgress.last_read_at))
        .join(Issue, Issue.id == ReadingProgress.issue_id)
        .join(Series, Series.id == Issue.series_id)
        .where(ReadingProgress.last_read_at.is_not(None))
        .group_by(Issue.series_id, Series.title)
        .order_by(func.max(ReadingProgress.last_read_at).desc())
        .limit(limite)
    )).all()
    return [UltimoLeido(str(sid), title, fecha) for sid, title, fecha in filas]


async def por_empezar(db: AsyncSession, limite: int = 6) -> list[PorEmpezar]:
    """Series con archivos y ninguna actividad de lectura."""
    con_archivos = select(File.issue_id).where(File.is_missing.is_(False))
    filas = (await db.execute(
        select(Issue.series_id, Series.title, func.count(func.distinct(Issue.id)))
        .join(Series, Series.id == Issue.series_id)
        .where(Issue.id.in_(con_archivos))
        .where(~Issue.series_id.in_(select(Issue.series_id).join(
            ReadingProgress, ReadingProgress.issue_id == Issue.id).where(
                ReadingProgress.status.in_([ReadingStatus.READING, ReadingStatus.COMPLETED]))))
        .group_by(Issue.series_id, Series.title)
        .order_by(func.count(func.distinct(Issue.id)).desc(), Series.title)
        .limit(limite)
    )).all()
    return [PorEmpezar(str(sid), title, int(total)) for sid, title, total in filas]


async def recien_incorporados(db: AsyncSession, limite: int = 6) -> list[RecienIncorporado]:
    """Primeras incorporaciones: serie nueva o número nuevo real.

    Excluye sustituciones y variantes porque solo cuenta el PRIMER archivo de
    cada Issue (`MIN(imported_at)`) y un Issue solo es «nuevo» si no existía
    material de la serie antes de su primera incorporación.
    """
    primera_serie = (select(File.issue_id, func.min(File.imported_at).label("imported_at"))
                     .where(File.issue_id.is_not(None), File.is_missing.is_(False))
                     .group_by(File.issue_id).subquery())
    min_serie = (select(Issue.series_id, func.min(File.imported_at).label("primera"))
                 .join(File, File.issue_id == Issue.id)
                 .where(File.is_missing.is_(False))
                 .group_by(Issue.series_id).subquery())
    filas = (await db.execute(
        select(Issue.series_id, Series.title, Issue.id, Issue.issue_number,
               primera_serie.c.imported_at, min_serie.c.primera)
        .join(primera_serie, primera_serie.c.issue_id == Issue.id)
        .join(Series, Series.id == Issue.series_id)
        .join(min_serie, min_serie.c.series_id == Issue.series_id)
        .order_by(primera_serie.c.imported_at.desc(), Issue.issue_number)
        .limit(limite * 8)
    )).all()
    vistas: set[str] = set()
    resultado: list[RecienIncorporado] = []
    for sid, title, iid, numero, importado, primera in filas:
        sid = str(sid)
        if sid in vistas:
            continue
        vistas.add(sid)
        tipo = "serie_nueva" if importado == primera else "numero_nuevo"
        resultado.append(RecienIncorporado(sid, title, str(iid), numero, importado, tipo))
        if len(resultado) >= limite:
            break
    return resultado
