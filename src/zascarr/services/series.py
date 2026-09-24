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

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    Character,
    Issue,
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
