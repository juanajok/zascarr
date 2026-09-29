"""
SeriesService — listado/filtrado de series (C1).

Fuente única de verdad para la rejilla de biblioteca (`web/library.py`)
y la API JSON (`api/series.py`) — mismo motivo que `WishlistService`:
una sola query, no una copia en cada router. Los filtros por personaje y
saga usan JOIN explícito, no `.any()` anidado: `Issue` no tiene una
relationship inversa a `StoryArcIssue` (solo `StoryArc.arc_issues`), así
que el join hace falta de todos modos ahí, y se usa el mismo estilo
también para personaje por consistencia y para evitar dos EXISTS
correlacionados anidados.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    Character,
    File,
    Issue,
    IssueFormat,
    MetadataSource,
    Publisher,
    Series,
    StoryArc,
    StoryArcIssue,
    issue_characters,
)


class SeriesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_series(
        self,
        page: int = 1,
        page_size: int = 20,
        tradition: str | None = None,
        status: str | None = None,
        search: str | None = None,
        publisher_id: UUID | None = None,
        character_id: UUID | None = None,
        story_arc_id: UUID | None = None,
    ) -> tuple[list[Series], int]:
        query = select(Series)
        needs_distinct = False

        if tradition:
            query = query.where(Series.tradition == tradition)
        if status:
            query = query.where(Series.status == status)
        if search:
            query = query.where(func.to_tsvector("spanish", Series.title).match(search))
        if publisher_id:
            query = query.where(Series.publisher_id == publisher_id)
        if character_id:
            query = (
                query.join(Issue, Issue.series_id == Series.id)
                .join(issue_characters, issue_characters.c.issue_id == Issue.id)
                .where(issue_characters.c.character_id == character_id)
            )
            needs_distinct = True
        if story_arc_id:
            query = (
                query.join(Issue, Issue.series_id == Series.id)
                .join(StoryArcIssue, StoryArcIssue.issue_id == Issue.id)
                .where(StoryArcIssue.story_arc_id == story_arc_id)
            )
            needs_distinct = True

        if needs_distinct:
            query = query.distinct()

        total = (await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )).scalar() or 0

        query = query.order_by(Series.sort_title, Series.start_year)
        query = query.offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(query)).scalars().all())
        return items, total

    async def list_publishers_with_series(self) -> list[Publisher]:
        """Solo editoriales que de verdad tienen alguna serie — un
        dropdown con publishers vacíos no ayuda a filtrar nada."""
        return list((await self.db.execute(
            select(Publisher)
            .where(Publisher.id.in_(select(Series.publisher_id).where(Series.publisher_id.is_not(None))))
            .order_by(Publisher.name)
        )).scalars().all())

    async def search_characters(self, query: str, limit: int = 20) -> list[Character]:
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(Character).where(Character.name.ilike(f"%{query}%")).order_by(Character.name).limit(limit)
        )).scalars().all())

    async def search_story_arcs(self, query: str, limit: int = 20) -> list[StoryArc]:
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(StoryArc).where(StoryArc.title.ilike(f"%{query}%")).order_by(StoryArc.title).limit(limit)
        )).scalars().all())


UNIDAD_DE_GRAPA = {MetadataSource.COMIC_VINE.value}


@dataclass(frozen=True)
class Huecos:
    """Huecos de una serie y si el cálculo merece confianza.

    `computable=False` significa "no hay con qué calcularlo", NO "no falta
    nada": la UI debe decirlo en vez de enseñar una lista inventada.
    """
    faltantes: list[int]
    computable: bool
    motivo: str | None = None


def compute_missing_issues(total_issues: int | None, numeros_poseidos: set[int]) -> list[int]:
    """Números 1..total_issues que la serie NO posee. Función pura.

    C2 (peer review): un Annual/especial no "cubre" el hueco de la grapa con
    el mismo número — eso lo garantiza `_numero_de_grapa`, que exige
    `format=SINGLE_ISSUE` y un número entero, en vez de comparar floats.
    """
    if not total_issues:
        return []
    return [i for i in range(1, total_issues + 1) if i not in numeros_poseidos]


def _numero_de_grapa(issue_number: str | None, formato) -> int | None:
    """Número entero si la fila ES una grapa numerada; `None` si no lo es.

    Solo una grapa (`SINGLE_ISSUE`) con número entero ocupa el hueco de la
    grapa de ese número. Un ómnibus/tomo #12 **no** es la grapa #12, y un
    `Annual 1` o un `1.5` tampoco tapan el hueco del nº 1 (regla de C2).
    """
    if formato != IssueFormat.SINGLE_ISSUE:
        return None
    if not issue_number or not issue_number.strip().isdigit():
        return None
    return int(issue_number.strip())


async def numeros_poseidos_por_serie(db: AsyncSession) -> dict[UUID, set[int]]:
    """Números de grapa poseídos, para TODAS las series, en una sola consulta.

    Versión agregada de `numeros_poseidos` para el dashboard (no N+1).
    """
    filas = (await db.execute(
        select(Issue.series_id, Issue.issue_number, Issue.format,
               exists().where(File.issue_id == Issue.id,
                              File.is_missing.is_(False)).label("disponible"))
    )).all()
    por_serie: dict[UUID, set[int]] = {}
    for series_id, numero, formato, disponible in filas:
        if not disponible:
            continue
        n = _numero_de_grapa(numero, formato)
        if n is not None:
            por_serie.setdefault(series_id, set()).add(n)
    return por_serie


async def numeros_poseidos(db: AsyncSession, series_id: UUID) -> set[int]:
    """Números de grapa que la serie POSEE de verdad, mirando el DISCO.

    Por qué no `Issue.sort_order` (2026-09-27): **ningún código de `main`
    escribe ese campo** — la única derivación que existió (`_derive_sort_order`)
    se quedó en una rama abandonada. Medido con `scripts/medicion/censo_huecos.py`
    sobre una muestra: 0/18 issues con `sort_order` y **52 huecos inventados**
    en 5 series, porque `compute_missing_issues(N, ∅)` devuelve `[1..N]`.

    Ahora la posesión sale de lo que hay en disco — un `File` con
    `is_missing=false`, el mismo criterio que ya usan los demás consumidores
    de "¿lo tengo?" (B7) — y del formato: solo una grapa cubre una grapa.
    """
    filas = (await db.execute(
        select(Issue.issue_number, Issue.format,
               exists().where(File.issue_id == Issue.id,
                              File.is_missing.is_(False)).label("disponible"))
        .where(Issue.series_id == series_id)
    )).all()
    poseidos: set[int] = set()
    for numero, formato, disponible in filas:
        if not disponible:
            continue
        n = _numero_de_grapa(numero, formato)
        if n is not None:
            poseidos.add(n)
    return poseidos


async def huecos_de_serie(db: AsyncSession, series: Series,
                          poseidos: set[int] | None = None) -> Huecos:
    """Huecos de una serie, diciendo — explícitamente — si el cálculo es fiable.

    Antes de restar hay que comprobar que las dos cantidades hablan de lo
    MISMO: `total_issues` lo copia el enricher del catálogo y **no siempre
    cuenta grapas** (AniList cuenta capítulos y sus ficheros son tomos). Si la
    unidad no está acreditada, `computable=False` en vez de una resta inventada.

    `poseidos` permite reutilizar una consulta ya hecha (la ficha de serie
    necesita el conjunto igualmente, para pintar los números presentes).
    """
    if not series.total_issues:
        return Huecos([], False, "la serie no tiene un total de números conocido")
    if series.metadata_source not in UNIDAD_DE_GRAPA:
        return Huecos(
            [], False,
            "el total de la serie no consta como número de grapas "
            f"({series.metadata_source or 'fuente desconocida'}), así que no se "
            "puede comparar con los números que hay en disco",
        )
    if poseidos is None:
        poseidos = await numeros_poseidos(db, series.id)
    return Huecos(compute_missing_issues(series.total_issues, poseidos), True, None)
