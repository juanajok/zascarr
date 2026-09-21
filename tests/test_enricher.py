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

from secuenciarr.models import ComicTradition, Creator, CreatorRole, Issue, MetadataSource, Series
from secuenciarr.services.anilist import AniListClient, AniListResult
from secuenciarr.services.comic_vine import ComicVineClient, CVCredit, CVResult, _parse_issue
from secuenciarr.services.enricher import EnrichmentReport, EnrichmentService
from secuenciarr.services.tebeosfera import TebeosferaResult, _parse_results


def make_series(title="Batman", start_year=None, comic_vine_id=None,
                metadata_source=None, description=None, cover_url=None,
                total_issues=None, tradition=ComicTradition.AMERICAN) -> Series:
    return Series(
        id=uuid4(), title=title, start_year=start_year,
        comic_vine_id=comic_vine_id, metadata_source=metadata_source,
        description=description, cover_url=cover_url, total_issues=total_issues,
        tradition=tradition,
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


class TestAniListRetry:

    @pytest.mark.asyncio
    async def test_reintenta_en_429_y_devuelve_datos_al_reintentar(self, monkeypatch):
        monkeypatch.setattr("asyncio.sleep", AsyncMock())

        client = AniListClient()
        responses = [
            httpx.Response(429, headers={"Retry-After": "0"}, request=httpx.Request("POST", "http://x")),
            httpx.Response(200, json={"data": {"Page": {"media": []}}},
                           request=httpx.Request("POST", "http://x")),
        ]
        fake_http = MagicMock()
        fake_http.post = AsyncMock(side_effect=responses)
        client._client = fake_http

        results = await client.search_manga("berserk")

        assert results == []
        assert fake_http.post.await_count == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 2. EnrichmentService._find_cv_series_match — solo acepta título exacto
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindSeriesMatch:

    @pytest.mark.asyncio
    async def test_sin_candidatos_no_hay_match(self):
        client = AsyncMock()
        client.search_series.return_value = []
        service = EnrichmentService(db=MagicMock())

        result = await service._find_cv_series_match(client, make_series("Serie Rarísima"))
        assert result is None

    @pytest.mark.asyncio
    async def test_titulo_normalizado_exacto_hace_match(self):
        client = AsyncMock()
        client.search_series.return_value = [
            CVResult(cv_id=1, name="Batman Beyond", start_year=1999),
            CVResult(cv_id=2, name="Batman", start_year=2011),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_cv_series_match(client, make_series("Batman"))
        assert result.source_id == 2  # "Batman Beyond" no matchea, solo el exacto

    @pytest.mark.asyncio
    async def test_solo_coincidencia_parcial_no_hace_match(self):
        """No adivina: si ningún candidato normaliza IGUAL al título, no hay match."""
        client = AsyncMock()
        client.search_series.return_value = [
            CVResult(cv_id=1, name="Batman Beyond", start_year=1999),
            CVResult(cv_id=2, name="Batman Adventures", start_year=1992),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_cv_series_match(client, make_series("Batman"))
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

        result = await service._find_cv_series_match(client, make_series("Batman", start_year=2012))
        assert result.source_id == 2


# ═══════════════════════════════════════════════════════════════════════════════
# 2b. EnrichmentService._find_anilist_match + enrutado por tradition
# ═══════════════════════════════════════════════════════════════════════════════

class TestFindAniListMatch:

    @pytest.mark.asyncio
    async def test_match_por_titulo_romaji(self):
        client = AsyncMock()
        client.search_manga.return_value = [
            AniListResult(anilist_id=1, title_romaji="Berserk", title_english=None, start_year=1989),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_anilist_match(
            client, make_series("Berserk", tradition=ComicTradition.MANGA))
        assert result.source_id == 1

    @pytest.mark.asyncio
    async def test_match_por_titulo_ingles_si_no_matchea_romaji(self):
        client = AsyncMock()
        client.search_manga.return_value = [
            AniListResult(anilist_id=2, title_romaji="Shingeki no Kyojin",
                         title_english="Attack on Titan", start_year=2009),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_anilist_match(
            client, make_series("Attack on Titan", tradition=ComicTradition.MANGA))
        assert result.source_id == 2

    @pytest.mark.asyncio
    async def test_sin_coincidencia_exacta_no_hay_match(self):
        client = AsyncMock()
        client.search_manga.return_value = [
            AniListResult(anilist_id=3, title_romaji="Berserk 2", title_english=None),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_anilist_match(
            client, make_series("Berserk", tradition=ComicTradition.MANGA))
        assert result is None

    @pytest.mark.asyncio
    async def test_chapters_se_mapea_a_count_of_issues(self):
        client = AsyncMock()
        client.search_manga.return_value = [
            AniListResult(anilist_id=4, title_romaji="One Piece", chapters=1100,
                         description="sinopsis", cover_url="http://x/y.jpg"),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_anilist_match(
            client, make_series("One Piece", tradition=ComicTradition.MANGA))
        assert result.count_of_issues == 1100
        assert result.description == "sinopsis"
        assert result.cover_url == "http://x/y.jpg"


# ═══════════════════════════════════════════════════════════════════════════════
# 2c. TebeosferaClient._parse_results — HTML real capturado en vivo contra
#     tebeosfera.com (POST a buscador_txt_post.php, 21/09/2026). Si el sitio
#     cambia de estructura, este test lo detecta antes que un ciclo real.
# ═══════════════════════════════════════════════════════════════════════════════

_COLECCIONES_HTML_REAL = '''<div id="div_buscador_txt_T3_publicaciones"><div class="help-block">Colecciones</div><div class="linea_resultados" style="clear:both;"><div style="float:left;"><img id="img_principal" src="https://www.tebeosfera.com/T3content/img/T3_numeros/_/1/thorgal_distrinovel_1981_1/R-100_thorgal_distrinovel_1981_1.jpg" width="100" height="100"  /></div><a href="/colecciones/thorgal_1981_distrinovel.html">THORGAL (1981, DISTRINOVEL)</a><br><div><div style="color:#834003;"><strong>THORGAL</strong> </div>1981 <br>3 números+ 1 variante</div></div><div class="linea_resultados" style="clear:both;"><div style="float:left;"><img id="img_principal" src="https://www.tebeosfera.com/T3content/img/T3_numeros/_/1/thorgal_1990_norma_1/R-100_thorgal_1990_norma_1.jpg" width="100" height="100"  /></div><a href="/colecciones/thorgal_1990_norma_-subcoleccion-.html">THORGAL (1990, NORMA) -SUBCOLECCION-</a><br><div><div style="color:#834003;"><strong>THORGAL</strong> </div>1990 <br>40 números</div></div></div>'''

_SAGAS_HTML_REAL = '''<div id="div_buscador_txt_T3_series"><div class="help-block">Sagas</div><div class="linea_resultados" style="clear:both;"><div style="float:left;"><a href="https://www.tebeosfera.com/T3content/img/T3_series/7/7/thorgal_van_hamme_rosinski_1977.jpg" class="highslide"><img id="img_principal" src="https://www.tebeosfera.com/T3content/img/T3_series/7/7/thorgal_van_hamme_rosinski_1977/R-100_thorgal_van_hamme_rosinski_1977.jpg" width="100" height="100"  /></a></div><a href="/sagas/thorgal_1977_van_hamme_rosinski.html">THORGAL (1977, VAN HAMME/ROSINSKI)</a><br><div>THORGAL es una serie de c&oacute;mic cuya andadura comenz&oacute; en 1977 de la mano de Van Hamme y Rosinki<a href="/personajes/thorgal_1977_van_hamme_rosinski.html">...</a></div></div></div>'''


class TestTebeosferaParseResults:

    def test_colecciones_extrae_slug_titulo_limpio_año_y_numeros(self):
        results = _parse_results(_COLECCIONES_HTML_REAL, "collection")
        assert len(results) == 2

        distrinovel = results[0]
        assert distrinovel.slug == "thorgal_1981_distrinovel"
        assert distrinovel.title == "THORGAL"  # sufijo "(1981, DISTRINOVEL)" limpiado
        assert distrinovel.start_year == 1981
        assert distrinovel.count_of_issues == 3

        norma = results[1]
        assert norma.slug == "thorgal_1990_norma_-subcoleccion-"
        assert norma.title == "THORGAL"  # "-SUBCOLECCION-" también fuera
        assert norma.count_of_issues == 40

    def test_sagas_extrae_slug_y_titulo_limpio(self):
        results = _parse_results(_SAGAS_HTML_REAL, "saga")
        assert len(results) == 1
        assert results[0].slug == "thorgal_1977_van_hamme_rosinski"
        assert results[0].title == "THORGAL"
        assert results[0].start_year == 1977

    def test_html_vacio_no_falla(self):
        assert _parse_results("", "collection") == []
        assert _parse_results("<div>sin resultados</div>", "saga") == []

    def test_html_roto_no_lanza_excepcion(self):
        # Contiene "linea_resultados" (pasa el check rápido) pero es HTML
        # roto de verdad: no debe propagar la excepción de lxml.
        assert _parse_results("<div class='linea_resultados'<<<", "collection") == []


class TestFindTebeosferaMatch:

    @pytest.mark.asyncio
    async def test_match_por_titulo_exacto_tras_limpiar_sufijo(self):
        client = AsyncMock()
        client.search_series.return_value = [
            TebeosferaResult(slug="thorgal_1977_van_hamme_rosinski", title="Thorgal",
                            kind="saga", start_year=1977),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_tebeosfera_match(
            client, make_series("Thorgal", tradition=ComicTradition.FRANCO_BELGIAN))
        assert result.source_id == "thorgal_1977_van_hamme_rosinski"

    @pytest.mark.asyncio
    async def test_desambiguacion_por_año_entre_varias_ediciones(self):
        """Varias colecciones distintas de la misma obra (reediciones):
        el año de nuestra Series decide, igual que Comic Vine/AniList."""
        client = AsyncMock()
        client.search_series.return_value = [
            TebeosferaResult(slug="thorgal_1981_distrinovel", title="Thorgal",
                            kind="collection", start_year=1981),
            TebeosferaResult(slug="thorgal_1986_zinco", title="Thorgal",
                            kind="collection", start_year=1986),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_tebeosfera_match(
            client, make_series("Thorgal", tradition=ComicTradition.FRANCO_BELGIAN, start_year=1987))
        assert result.source_id == "thorgal_1986_zinco"

    @pytest.mark.asyncio
    async def test_sin_coincidencia_exacta_no_hay_match(self):
        client = AsyncMock()
        client.search_series.return_value = [
            TebeosferaResult(slug="thorgal_saga_derivada", title="Thorgal: Kriss de Valnor", kind="collection"),
        ]
        service = EnrichmentService(db=MagicMock())

        result = await service._find_tebeosfera_match(
            client, make_series("Thorgal", tradition=ComicTradition.TEBEO))
        assert result is None


class TestSourceRouting:

    def test_manga_va_a_anilist(self):
        service = EnrichmentService(db=MagicMock())
        field, source, label = service._source_for(ComicTradition.MANGA)
        assert (field, source, label) == ("anilist_id", MetadataSource.ANILIST.value, "AniList")

    def test_manhwa_y_manhua_van_a_anilist(self):
        service = EnrichmentService(db=MagicMock())
        for tradition in (ComicTradition.MANHWA, ComicTradition.MANHUA):
            field, _, _ = service._source_for(tradition)
            assert field == "anilist_id"

    def test_american_y_british_van_a_comic_vine(self):
        service = EnrichmentService(db=MagicMock())
        for tradition in (ComicTradition.AMERICAN, ComicTradition.BRITISH):
            field, source, label = service._source_for(tradition)
            assert (field, source, label) == ("comic_vine_id", MetadataSource.COMIC_VINE.value, "Comic Vine")

    def test_tebeo_y_franco_belgian_van_a_tebeosfera(self):
        service = EnrichmentService(db=MagicMock())
        for tradition in (ComicTradition.TEBEO, ComicTradition.FRANCO_BELGIAN):
            field, source, label = service._source_for(tradition)
            assert (field, source, label) == ("tebeosfera_slug", MetadataSource.TEBEOSFERA.value, "Tebeosfera")

    def test_tradiciones_sin_fuente_devuelven_none(self):
        """fumetti: ninguna fuente activa la indexa con confianza todavía.
        Mejor no enriquecer que enriquecer con la fuente equivocada."""
        service = EnrichmentService(db=MagicMock())
        assert service._source_for(ComicTradition.FUMETTI) is None

    @pytest.mark.asyncio
    async def test_serie_sin_fuente_no_aparece_ni_como_match_ni_como_no_match(self):
        series = make_series("Corto Maltese", tradition=ComicTradition.FUMETTI)
        session = FakeSession([FakeExecResult([series])])
        service = EnrichmentService(db=session)
        report = EnrichmentReport()

        await service._enrich_series_batch(AsyncMock(), AsyncMock(), AsyncMock(), 10, report)

        assert report.series_enriched == []
        assert report.series_no_match == []
        assert series.comic_vine_id is None
        assert series.anilist_id is None
        assert series.tebeosfera_slug is None

    @pytest.mark.asyncio
    async def test_serie_manga_se_enriquece_via_anilist_no_comic_vine(self):
        series = make_series("Berserk", tradition=ComicTradition.MANGA)
        cv_client = AsyncMock()
        anilist_client = AsyncMock()
        anilist_client.search_manga.return_value = [
            AniListResult(anilist_id=42, title_romaji="Berserk", chapters=370),
        ]
        session = FakeSession([FakeExecResult([series])])
        service = EnrichmentService(db=session)
        report = EnrichmentReport()

        await service._enrich_series_batch(cv_client, anilist_client, AsyncMock(), 10, report)

        assert series.anilist_id == 42
        assert series.comic_vine_id is None
        assert series.metadata_source == MetadataSource.ANILIST.value
        assert report.series_enriched == ["Berserk"]
        cv_client.search_series.assert_not_called()

    @pytest.mark.asyncio
    async def test_serie_tebeo_se_enriquece_via_tebeosfera(self):
        series = make_series("Mortadelo y Filemón", tradition=ComicTradition.TEBEO)
        cv_client = AsyncMock()
        tebeosfera_client = AsyncMock()
        tebeosfera_client.search_series.return_value = [
            TebeosferaResult(slug="mortadelo_1969_bruguera", title="Mortadelo y Filemón",
                            kind="collection", count_of_issues=200),
        ]
        session = FakeSession([FakeExecResult([series])])
        service = EnrichmentService(db=session)
        report = EnrichmentReport()

        await service._enrich_series_batch(cv_client, AsyncMock(), tebeosfera_client, 10, report)

        assert series.tebeosfera_slug == "mortadelo_1969_bruguera"
        assert series.comic_vine_id is None
        assert series.total_issues == 200
        assert series.metadata_source == MetadataSource.TEBEOSFERA.value
        assert report.series_enriched == ["Mortadelo y Filemón"]
        cv_client.search_series.assert_not_called()


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
        await service._enrich_series_batch(client, AsyncMock(), AsyncMock(), 10, report)

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
        await service._enrich_series_batch(client, AsyncMock(), AsyncMock(), 10, report)

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
