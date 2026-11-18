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
    titulo: str | None
    imported_at: datetime
    tipo: str  # "serie_nueva" | "numero_nuevo"


def _es_secuencial(numero: str | None) -> bool:
    return bool(numero and _NUMERO_SECUENCIAL.match(numero))


async def continuar_leyendo(db: AsyncSession, limite: int = 6) -> list[ContinuarLeyendo]:
    """Números en curso o el siguiente tras el último leído, con archivo local.

    Primero acota las series con actividad por `MAX(last_read_at)` (CTE) y solo
    carga los números de esas series; el anual/especial se acepta como
    candidato cuando no hay siguiente regular, sin romper el orden canónico.
    """
    series_act = (select(Issue.series_id.label("series_id"),
                         func.max(ReadingProgress.last_read_at).label("actividad"))
                  .join(ReadingProgress, ReadingProgress.issue_id == Issue.id)
                  .where(ReadingProgress.status.in_(
                      [ReadingStatus.READING, ReadingStatus.COMPLETED]))
                  .group_by(Issue.series_id)
                  .order_by(func.max(ReadingProgress.last_read_at).desc())
                  .limit(max(limite * 4, limite)).subquery())
    filas = (await db.execute(
        select(Issue.series_id, Series.title, Issue.id, Issue.issue_number,
               Issue.title.label("issue_title"), Issue.sort_order, Issue.page_count,
               ReadingProgress.status, ReadingProgress.current_page,
               series_act.c.actividad)
        .join(Series, Series.id == Issue.series_id)
        .join(series_act, series_act.c.series_id == Issue.series_id)
        .outerjoin(ReadingProgress, ReadingProgress.issue_id == Issue.id)
        .where(Issue.id.in_(select(File.issue_id).where(
            File.issue_id.is_not(None), File.is_missing.is_(False))))
        .order_by(series_act.c.actividad.desc(), Issue.sort_order.asc().nulls_last(),
                  Issue.issue_number)
        .limit(max(limite * 120, 240))
    )).all()
    por_serie: dict[str, list] = {}
    actividad: dict[str, object] = {}
    for fila in filas:
        sid = str(fila.series_id)
        por_serie.setdefault(sid, []).append(fila)
        actividad[sid] = fila.actividad
    resultado: list[ContinuarLeyendo] = []
    for serie_id in sorted(por_serie, key=lambda x: actividad[x], reverse=True):
        issues = por_serie[serie_id]
        issues.sort(key=lambda f: (f.sort_order is None, f.sort_order or 0.0,
                                   natural_key(f.issue_number or "")))
        elegido = next((f for f in issues if f.status is ReadingStatus.READING), None)
        if elegido is None:
            leidos = [i for i, f in enumerate(issues) if f.status is ReadingStatus.COMPLETED]
            if not leidos:
                continue
            candidatos = issues[leidos[-1] + 1:]
            elegido = next((f for f in candidatos if _es_secuencial(f.issue_number)), None)
            if elegido is None and candidatos:
                elegido = candidatos[0]
        if elegido is None:
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
    min_serie = (select(Issue.series_id, func.min(File.imported_at).label("primera"),
                        func.max(File.imported_at).label("ultima"),
                        func.count(func.distinct(Issue.id)).label("numeros"))
                 .join(File, File.issue_id == Issue.id)
                 .where(File.is_missing.is_(False))
                 .group_by(Issue.series_id).subquery())
    filas = (await db.execute(
        select(Issue.series_id, Series.title, Issue.id, Issue.issue_number,
               Issue.title, primera_serie.c.imported_at, min_serie.c.primera,
               min_serie.c.numeros, min_serie.c.ultima, Issue.created_at)
        .join(primera_serie, primera_serie.c.issue_id == Issue.id)
        .join(Series, Series.id == Issue.series_id)
        .join(min_serie, min_serie.c.series_id == Issue.series_id)
        .order_by(primera_serie.c.imported_at.desc(), Series.title,
                  Issue.sort_order.asc().nulls_last(), Issue.issue_number)
        .limit(limite * 8)
    )).all()
    vistas: set[str] = set()
    resultado: list[RecienIncorporado] = []
    for sid, title, iid, numero, issue_title, importado, primera, numeros, ultima, creado in filas:
        sid = str(sid)
        if sid in vistas:
            continue
        # Sustitución: el Issue ya existía antes de que llegara este archivo y
        # la serie ya tenía material. No es una incorporación nueva.
        if (creado is not None and importado is not None and primera is not None
                and creado < importado and primera < importado):
            continue
        # Una serie con varios números importados en momentos distintos ya existía:
        # su primera incorporación es la base, no una novedad. Un pack nuevo entra
        # con todos los números en el mismo instante y sí es «serie_nueva».
        if importado == primera and numeros > 1 and ultima != primera:
            continue
        vistas.add(sid)
        tipo = "serie_nueva" if importado == primera else "numero_nuevo"
        resultado.append(RecienIncorporado(
            sid, title, str(iid), numero, issue_title, importado, tipo))
        if len(resultado) >= limite:
            break
    return resultado
