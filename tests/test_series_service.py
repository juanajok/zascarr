"""
tests/test_series_service.py

Suite de SeriesService (C1). Los filtros simples (tradición/editorial/
búsqueda) se prueban con FakeSession, igual que el resto de la suite.
Los filtros por personaje/saga usan JOIN M:N reales — un JOIN mal
construido puede compilar y ejecutar sin error y aun así devolver el
conjunto vacío o incorrecto, invisible con datos falsos. Esos dos casos
se prueban contra Postgres real (TEST_DATABASE_URL), mismo patrón que
tests/test_title_norm.py — se saltan si no está definida.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete

from secuenciarr.models import ComicTradition, Publisher, Series
from secuenciarr.services.series import SeriesService

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return FakeScalarResult(self._value)

    def scalar(self):
        return self._value


class FakeSession:
    def __init__(self, queue: list):
        self._queue = list(queue)

    async def execute(self, _statement):
        return self._queue.pop(0)


def make_series(title="Batman", tradition=ComicTradition.AMERICAN, publisher_id=None) -> Series:
    return Series(id=uuid4(), title=title, tradition=tradition, publisher_id=publisher_id)


class TestListSeriesFiltrosSimples:

    @pytest.mark.asyncio
    async def test_sin_filtros_devuelve_todo(self):
        series = [make_series("Batman"), make_series("Sandman")]
        session = FakeSession([FakeExecResult(2), FakeExecResult(series)])
        items, total = await SeriesService(session).list_series()
        assert total == 2
        assert items == series

    @pytest.mark.asyncio
    async def test_filtro_publisher_id_no_rompe_la_query(self):
        publisher_id = uuid4()
        series = [make_series("Batman", publisher_id=publisher_id)]
        session = FakeSession([FakeExecResult(1), FakeExecResult(series)])
        items, total = await SeriesService(session).list_series(publisher_id=publisher_id)
        assert total == 1
        assert items == series


class TestPublishersConSerie:

    @pytest.mark.asyncio
    async def test_devuelve_publishers(self):
        publishers = [Publisher(id=uuid4(), name="Norma")]
        session = FakeSession([FakeExecResult(publishers)])
        result = await SeriesService(session).list_publishers_with_series()
        assert result == publishers


class TestSearchCharactersYStoryArcs:

    @pytest.mark.asyncio
    async def test_personaje_query_vacia_no_consulta_bd(self):
        session = FakeSession([])
        result = await SeriesService(session).search_characters("   ")
        assert result == []

    @pytest.mark.asyncio
    async def test_saga_query_vacia_no_consulta_bd(self):
        session = FakeSession([])
        result = await SeriesService(session).search_story_arcs("")
        assert result == []


# ═══════════════════════════════════════════════════════════════════════════
# Filtros por JOIN real (personaje/saga) — solo con Postgres real.
# ═══════════════════════════════════════════════════════════════════════════

pytestmark_live = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="requiere TEST_DATABASE_URL (Postgres real) — el JOIN M:N no se puede verificar con FakeSession",
)


@pytestmark_live
class TestFiltrosPorJoinRealesContraPostgres:

    @pytest.fixture
    async def session(self):
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
        engine = create_async_engine(TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
        async with AsyncSession(engine, expire_on_commit=False) as s:
            yield s
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_filtro_por_personaje_solo_devuelve_la_serie_correcta(self, session):
        from secuenciarr.models import Character, Issue, issue_characters

        con_personaje = Series(title=f"Con Personaje {uuid4()}", tradition=ComicTradition.AMERICAN)
        sin_personaje = Series(title=f"Sin Personaje {uuid4()}", tradition=ComicTradition.AMERICAN)
        session.add_all([con_personaje, sin_personaje])
        await session.flush()

        issue = Issue(series_id=con_personaje.id, issue_number="1")
        character = Character(name=f"Batman {uuid4()}")
        session.add_all([issue, character])
        await session.flush()
        # Insert directo en la tabla de asociación en vez de
        # issue.characters.append(...): tocar la relationship lazy fuera
        # de un await explícito dispara MissingGreenlet (mismo cuidado
        # que documenta enricher.py._apply_credits).
        await session.execute(issue_characters.insert().values(issue_id=issue.id, character_id=character.id))
        await session.commit()

        try:
            items, total = await SeriesService(session).list_series(character_id=character.id)
            assert total == 1
            assert items == [con_personaje]
        finally:
            await session.delete(issue)
            await session.delete(character)
            await session.delete(con_personaje)
            await session.delete(sin_personaje)
            await session.commit()

    @pytest.mark.asyncio
    async def test_filtro_por_saga_solo_devuelve_la_serie_correcta(self, session):
        from secuenciarr.models import Issue, StoryArc, StoryArcIssue

        con_saga = Series(title=f"Con Saga {uuid4()}", tradition=ComicTradition.AMERICAN)
        sin_saga = Series(title=f"Sin Saga {uuid4()}", tradition=ComicTradition.AMERICAN)
        session.add_all([con_saga, sin_saga])
        await session.flush()

        issue = Issue(series_id=con_saga.id, issue_number="1")
        arc = StoryArc(title=f"Arco {uuid4()}")
        session.add_all([issue, arc])
        await session.flush()
        session.add(StoryArcIssue(story_arc_id=arc.id, issue_id=issue.id, reading_order=1))
        await session.commit()

        try:
            items, total = await SeriesService(session).list_series(story_arc_id=arc.id)
            assert total == 1
            assert items == [con_saga]
        finally:
            await session.execute(delete(StoryArcIssue).where(StoryArcIssue.story_arc_id == arc.id))
            await session.delete(issue)
            await session.delete(arc)
            await session.delete(con_saga)
            await session.delete(sin_saga)
            await session.commit()
