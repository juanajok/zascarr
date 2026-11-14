"""Búsqueda e importación de sagas desde Fandom DC (BL-C4/#158 ampliación).

Solo se enlazan números que YA existen en la biblioteca local. Nunca se
crean series ni issues, y no se copia prosa de la wiki: únicamente el
título de la página y sus referencias de números, con atribución.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Issue, Series, StoryArc, StoryArcIssue
from zascarr.services.fandom import (
    FandomArc,
    FandomClient,
    FandomSearchPage,
    referencia_de_issue,
)

ORIGEN = "fandom_dc"


@dataclass(frozen=True)
class FilaArcoFandom:
    page_title: str
    base: str
    numero: str
    series_id: str | None = None
    serie: str | None = None
    issue_id: str | None = None
    coincide: bool = False
    faltan: bool = False


@dataclass
class PreviaArcoFandom:
    page_title: str
    title: str
    filas: list[FilaArcoFandom] = field(default_factory=list)
    coinciden: int = 0
    faltan: int = 0


@dataclass
class ResultadoImportacionArco:
    arco_id: str
    creados: int = 0
    actualizados: int = 0
    enlazados: int = 0


async def buscar_arcos_fandom(
    titulo: str, cliente: FandomClient, limit: int = 6,
) -> list[FandomSearchPage]:
    """Busca páginas de arcos; no filtra por plantilla ni toca la BD."""
    consulta = (titulo or "").strip()
    if not consulta:
        return []
    return await cliente.search_pages(consulta, limit=limit)


async def _referencias_por_pagina(
    arco: FandomArc,
) -> list[tuple[str, str, str]]:
    """(page_title, base, número) de las referencias válidas, sin repetir."""
    referencias: list[tuple[str, str, str]] = []
    vistas: set[str] = set()
    for pagina in arco.issues:
        if pagina in vistas:
            continue
        vista = referencia_de_issue(pagina)
        if vista is None:
            continue
        vistas.add(pagina)
        base, numero = vista
        referencias.append((pagina, base, numero))
    return referencias


async def _locales_por_referencia(
    db: AsyncSession, referencias: list[tuple[str, str, str]],
) -> dict[tuple[str, str], tuple[Series, Issue]]:
    """Resuelve series e issues locales en DOS consultas (sin N+1)."""
    bases = {base for _pagina, base, _numero in referencias}
    if not bases:
        return {}
    series = (await db.execute(
        select(Series).where(Series.fandom_dc_slug.in_(bases))
    )).scalars().all()
    por_base = {s.fandom_dc_slug: s for s in series}
    series_ids = [s.id for s in por_base.values()]
    numeros = {numero for _pagina, _base, numero in referencias}
    if not series_ids:
        return {}
    issues = (await db.execute(
        select(Issue).where(
            Issue.series_id.in_(series_ids), Issue.issue_number.in_(numeros))
    )).scalars().all()
    por_serie_numero = {(str(i.series_id), i.issue_number): i for i in issues}
    locales: dict[tuple[str, str], tuple[Series, Issue]] = {}
    for _pagina, base, numero in referencias:
        serie = por_base.get(base)
        if serie is None:
            continue
        issue = por_serie_numero.get((str(serie.id), numero))
        if issue is not None:
            locales[(base, numero)] = (serie, issue)
    return locales


async def previsualizar_arco_fandom(
    db: AsyncSession, page_title: str, cliente: FandomClient,
) -> PreviaArcoFandom | None:
    """Lee el arco y compara sus números con la biblioteca; no crea nada."""
    arco = await cliente.get_arc(page_title)
    if arco is None:
        return None
    referencias = await _referencias_por_pagina(arco)
    locales = await _locales_por_referencia(db, referencias)
    filas: list[FilaArcoFandom] = []
    for pagina, base, numero in referencias:
        local = locales.get((base, numero))
        if local is None:
            filas.append(FilaArcoFandom(
                page_title=pagina, base=base, numero=numero, faltan=True))
        else:
            serie, issue = local
            filas.append(FilaArcoFandom(
                page_title=pagina, base=base, numero=numero,
                series_id=str(serie.id), serie=serie.title,
                issue_id=str(issue.id), coincide=True))
    return PreviaArcoFandom(
        page_title=arco.page_title, title=arco.title, filas=filas,
        coinciden=sum(1 for f in filas if f.coincide),
        faltan=sum(1 for f in filas if f.faltan),
    )


async def _arco_de_fandom(db: AsyncSession, page_title: str) -> StoryArc | None:
    return (await db.execute(
        select(StoryArc).where(
            StoryArc.metadata_["fandom_dc"].astext == page_title)
    )).scalars().first()


async def importar_arco_fandom(
    db: AsyncSession, page_title: str, cliente: FandomClient,
) -> ResultadoImportacionArco | None:
    """Crea/actualiza la saga de Fandom y enlaza solo números locales.

    No borra enlaces previos, no crea series/issues y no guarda descripción
    ni prosa de la wiki. La identidad es `metadata_["fandom_dc"]`; los arcos
    manuales o de otra fuente no se adoptan.
    """
    arco = await cliente.get_arc(page_title)
    if arco is None:
        return None
    referencias = await _referencias_por_pagina(arco)
    locales = await _locales_por_referencia(db, referencias)
    fila = await _arco_de_fandom(db, arco.page_title)
    creados = actualizados = 0
    if fila is None:
        fila = StoryArc(
            title=(arco.title or arco.page_title)[:500],
            metadata_={"origen": ORIGEN, "fandom_dc": arco.page_title},
        )
        db.add(fila)
        await db.flush()
        creados = 1
    else:
        fila.metadata_ = {**(fila.metadata_ or {}), "origen": ORIGEN,
                          "fandom_dc": arco.page_title}
        if arco.title and fila.title != arco.title[:500]:
            fila.title = arco.title[:500]
        actualizados = 1

    existentes = {
        e.issue_id: e
        for e in (await db.execute(
            select(StoryArcIssue).where(StoryArcIssue.story_arc_id == fila.id)
        )).scalars().all()
    }
    enlazados = 0
    orden = 0
    for _pagina, base, numero in referencias:
        local = locales.get((base, numero))
        if local is None:
            continue
        orden += 1
        _serie, issue = local
        enlace = existentes.get(issue.id)
        if enlace is None:
            db.add(StoryArcIssue(story_arc_id=fila.id, issue_id=issue.id,
                                 reading_order=orden))
            enlazados += 1
        elif enlace.reading_order != orden:
            enlace.reading_order = orden
    await db.flush()
    return ResultadoImportacionArco(
        arco_id=str(fila.id), creados=creados, actualizados=actualizados,
        enlazados=enlazados)


def url_de_atribucion(page_title: str) -> str | None:
    """URL pública de la página de Fandom, solo si el título es un segmento válido."""
    titulo = (page_title or "").strip().replace(" ", "_")
    if not titulo or "/" in titulo or "\\" in titulo or ".." in titulo:
        return None
    return f"https://dc.fandom.com/wiki/{titulo}"
