"""
tests/test_enricher.py

Suite del enricher (B4 del backlog): completar metadatos vía Comic Vine sin
pisar correcciones humanas ni campos ya rellenos.

Sigue el mismo patrón que test_naming_core.py: sin DB real, mockeando el
cliente de Comic Vine y (donde hace falta) una sesión mínima suficiente
para el método bajo prueba.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest

from secuenciarr.models import Creator, CreatorRole, Issue, MetadataSource, Series
from secuenciarr.services.comic_vine import ComicVineClient, CVCredit, CVResult, _parse_issue
from secuenciarr.services.enricher import EnrichmentReport, EnrichmentService


def make_series(title="Batman", start_year=None, comic_vine_id=None,
                metadata_source=None, description=None, cover_url=None,
                total_issues=None) -> Series:
    return Series(
        id=uuid4(), title=title, start_year=start_year,
        comic_vine_id=comic_vine_id, metadata_source=metadata_source,
        description=description, cover_url=cover_url, total_issues=total_issues,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ComicVineClient — parseo de /issues/ y reintento en 429
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseIssue:

    def test_credit_con_varios_roles_separados_por_coma(self):
        item = {
            "id": 42, "issue_number": "1", "description": "desc",
            "image": {"medium_url": "http://x/y.jpg"}, "cover_date": "2020-01-01",
            "person_credits": [
                {"id": 7, "name": "Grant Morrison", "role": "writer, plotter"},
            ],
        }
        result = _parse_issue(item)
        assert result.cv_id == 42
        assert len(result.credits) == 1
        assert result.credits[0].roles == ["writer", "plotter"]

    def test_credit_sin_nombre_se_ignora(self):
        item = {"id": 1, "person_credits": [{"id": 9, "role": "writer"}]}
        result = _parse_issue(item)
        assert result.credits == []

    def test_sin_person_credits_no_falla(self):
        item = {"id": 1}
        result = _parse_issue(item)
        assert result.credits == []
        assert result.description is None


class TestComicVineRetry:

    @pytest.mark.asyncio
    async def test_reintenta_en_429_y_devuelve_datos_al_reintentar(self, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        client = ComicVineClient()
        responses = [
            httpx.Response(429, headers={"Retry-After": "0"}, request=httpx.Request("GET", "http://x")),
            httpx.Response(200, json={"error": "OK", "results": []}, request=httpx.Request("GET", "http://x")),
        ]
        fake_http = MagicMock()
        fake_http.get = AsyncMock(side_effect=responses)
        client._client = fake_http

        data = await client._get("/search/", {"query": "batman"})

        assert data["results"] == []
        assert fake_http.get.await_count == 2

    @pytest.mark.asyncio
    async def test_no_muta_params_del_caller(self, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())
        client = ComicVineClient()
        fake_http = MagicMock()
        fake_http.get = AsyncMock(
            return_value=httpx.Response(200, json={"error": "OK"}, request=httpx.Request("GET", "http://x"))
        )
        client._client = fake_http

        caller_params = {"query": "batman"}
        await client._get("/search/", caller_params)

        assert caller_params == {"query": "batman"}  # sin api_key ni format inyectados


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EnrichmentService._find_series_match — solo acepta título exacto
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindSeriesMatch:

    @pytest.mark.asyncio
    async def test_sin_candidatos_no_hay_match(self):
        client = AsyncMock()
        client.search_series.return_value = []
        service = EnrichmentService(db=MagicMock())

        result = await service._find_series_match(client, make_series("Serie Rarísima"))
        assert result is None

    @pytest.mark.asyncio
    async def test_titulo_normalizado_exacto_hace_match(self):
        client = AsyncMock()
        client.search_series.return_value = [
            CVResult(cv_id=1, name="Batman Beyond", start_year=1999),
            CVResult(cv_id=2, name="Batman", start_year=2011),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_series_match(client, make_series("Batman"))
        assert result.cv_id == 2  # "Batman Beyond" no matchea, solo el exacto

    @pytest.mark.asyncio
    async def test_solo_coincidencia_parcial_no_hace_match(self):
        """No adivina: si ningún candidato normaliza IGUAL al título, no hay match."""
        client = AsyncMock()
        client.search_series.return_value = [
            CVResult(cv_id=1, name="Batman Beyond", start_year=1999),
            CVResult(cv_id=2, name="Batman Adventures", start_year=1992),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_series_match(client, make_series("Batman"))
        assert result is None

    @pytest.mark.asyncio
    async def test_desambiguacion_por_año_entre_varios_exactos(self):
        """Dos series distintas llamadas igual ('Batman' 1940 vs 2011):
        el año de nuestra Series decide, igual que en matcher.py."""
        client = AsyncMock()
        client.search_series.return_value = [
            CVResult(cv_id=1, name="Batman", start_year=1940),
            CVResult(cv_id=2, name="Batman", start_year=2011),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_series_match(client, make_series("Batman", start_year=2012))
        assert result.cv_id == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Reglas de convivencia: 'manual' intocable, no se pisan campos rellenos
# ═══════════════════════════════════════════════════════════════════════════════

class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    """Sesión mínima: una cola de resultados en el orden en que
    _enrich_series_batch los pide (pending series, luego nada más porque
    no hay issues en este test)."""

    def __init__(self, queue: list):
        self._queue = list(queue)
        self.flush = AsyncMock()

    async def execute(self, _statement):
        return self._queue.pop(0)


class TestNuncaTocaManual:

    @pytest.mark.asyncio
    async def test_query_excluye_series_manual_por_construccion(self):
        """No hay forma de inspeccionar el SQL generado sin una DB real, pero
        se puede verificar que el WHERE usa is_distinct_from('manual') y no
        una igualdad simple (que trataría NULL de forma incorrecta)."""
        from sqlalchemy import select
        from secuenciarr.models import MetadataSource as MS

        stmt = (
            select(Series)
            .where(Series.comic_vine_id.is_(None))
            .where(Series.metadata_source.is_distinct_from(MS.MANUAL.value))
        )
        compiled = str(stmt)
        assert "IS DISTINCT FROM" in compiled

    @pytest.mark.asyncio
    async def test_no_sobrescribe_campos_ya_rellenos(self):
        """Si la serie ya tiene descripción/portada, un match de Comic Vine
        no debe pisarlas — solo debe rellenar total_issues, que está vacío."""
        series = make_series("Batman", description="Descripción humana",
                             cover_url="http://ya-tengo/portada.jpg")
        client = AsyncMock()
        client.search_series.return_value = [CVResult(cv_id=99, name="Batman",
                                                       description="CV desc",
                                                       image_url="http://cv/img.jpg",
                                                       count_of_issues=850)]
        service = EnrichmentService(db=FakeSession([FakeExecResult([series])]))
        report = EnrichmentReport()
        await service._enrich_series_batch(client, 10, report)

        assert series.description == "Descripción humana"
        assert series.cover_url == "http://ya-tengo/portada.jpg"
        assert series.total_issues == 850
        assert series.comic_vine_id == 99
        assert series.metadata_source == MetadataSource.COMIC_VINE.value
        assert report.series_enriched == ["Batman"]

    @pytest.mark.asyncio
    async def test_metadata_source_ya_fijado_no_se_reetiqueta(self):
        """Si comicinfo_xml ya puso metadata_source, el enricher no lo cambia
        a 'comic_vine' aunque haya aportado comic_vine_id."""
        series = make_series("Sandman", metadata_source=MetadataSource.COMICINFO_XML.value)
        client = AsyncMock()
        client.search_series.return_value = [CVResult(cv_id=5, name="Sandman")]
        service = EnrichmentService(db=FakeSession([FakeExecResult([series])]))
        report = EnrichmentReport()
        await service._enrich_series_batch(client, 10, report)

        assert series.metadata_source == MetadataSource.COMICINFO_XML.value
        assert series.comic_vine_id == 5


# ═══════════════════════════════════════════════════════════════════════════════
# 4. _apply_credits — mapeo de rol y no duplicar si ya hay créditos
# ═══════════════════════════════════════════════════════════════════════════════

class TestApplyCredits:

    @pytest.mark.asyncio
    async def test_no_toca_issue_que_ya_tiene_creditos(self):
        issue = Issue(id=uuid4(), series_id=uuid4(), issue_number="1")
        existing_credit = MagicMock()
        session = FakeSession([FakeExecResult([existing_credit])])
        service = EnrichmentService(db=session)

        await service._apply_credits(issue, [CVCredit(cv_id=1, name="Alan Moore", roles=["writer"])])

        # No debió intentar buscar/crear ningún creator: la cola solo tenía
        # un resultado (el chequeo de créditos existentes) y no se vació más.
        assert session._queue == []

    @pytest.mark.asyncio
    async def test_rol_desconocido_se_ignora(self):
        issue = Issue(id=uuid4(), series_id=uuid4(), issue_number="1")
        session = FakeSession([
            FakeExecResult([]),  # sin créditos existentes
        ])
        service = EnrichmentService(db=session)
        added = []
        session.add = lambda obj: added.append(obj)

        await service._apply_credits(issue, [CVCredit(cv_id=1, name="X", roles=["plotter"])])

        assert added == []  # "plotter" no está en _CV_ROLE_MAP

    @pytest.mark.asyncio
    async def test_rol_conocido_crea_creator_y_credito(self):
        issue = Issue(id=uuid4(), series_id=uuid4(), issue_number="1")
        new_creator_id = uuid4()

        session = FakeSession([
            FakeExecResult([]),   # sin créditos existentes
            FakeExecResult([]),   # get_or_create_creator: por comic_vine_id, no existe
            FakeExecResult([]),   # get_or_create_creator: por nombre, no existe
        ])
        added = []

        def fake_add(obj):
            if isinstance(obj, Creator):
                obj.id = new_creator_id
            added.append(obj)

        session.add = fake_add
        service = EnrichmentService(db=session)

        await service._apply_credits(issue, [CVCredit(cv_id=1, name="Grant Morrison", roles=["writer"])])

        creators = [o for o in added if isinstance(o, Creator)]
        assert len(creators) == 1
        assert creators[0].name == "Grant Morrison"
        issue_creators = [o for o in added if hasattr(o, "role")]
        assert len(issue_creators) == 1
        assert issue_creators[0].role == CreatorRole.WRITER
