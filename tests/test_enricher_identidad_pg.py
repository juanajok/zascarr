# ruff: noqa: E501
"""El enriquecedor no empareja por título una serie que ya tiene identidad elegida (cualquier fuente, GCD incluida).

Antes la query de `_enrich_series_batch` miraba `comic_vine_id`, `anilist_id` y `tebeosfera_slug` pero no `gcd_id`: a
una serie dada de alta desde GCD le podía **añadir** un id de Comic Vine por igualdad de título. Conservar `gcd_id` y
`metadata_source` no demuestra que ese otro id sea de la misma edición. Pruebas sobre Postgres real (la query se
ejecuta de verdad); las fuentes se simulan. Se saltan sin `TEST_DATABASE_URL`.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, Series
from zascarr.services.enricher import EnrichmentReport, EnrichmentService

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    yield b
    await b.cerrar()


class Fuente:
    """Un cliente de fuente falso: anota lo que se le pregunta y siempre «encuentra» el mismo título."""

    def __init__(self, *, genres=None, characters=None):
        self.consultas: list[str] = []
        self.genres = list(genres or [])
        self.characters = list(characters or [])

    async def search_series(self, titulo, limit=10):
        self.consultas.append(titulo)
        return [SimpleNamespace(name=titulo, cv_id=999999, start_year=None, description="d",
                                image_url=None, count_of_issues=None, slug="slug_nuevo", title=titulo,
                                kind="collection", cover_url=None, site_url=None)]

    async def search_manga(self, titulo, limit=10):
        self.consultas.append(titulo)
        return [SimpleNamespace(title_romaji=titulo, title_english=None, anilist_id=888888, start_year=None,
                                description="d", cover_url=None, chapters=None,
                                genres=list(self.genres))]

    async def find_issue(self, _volume_id, _numero):
        from zascarr.services.comic_vine import CVIssueResult
        return CVIssueResult(cv_id=777777, characters=list(self.characters))


async def sembrar(b: Banco, titulo: str, tradicion=ComicTradition.AMERICAN, **ids) -> UUID:
    sid = uuid4()
    async with b.fabrica() as s:
        s.add(Series(id=sid, title=titulo, tradition=tradicion, **ids))
        await s.commit()
    return sid


async def enriquecer(b: Banco, cv=None, anilist=None, tebeosfera=None):
    informe = EnrichmentReport()
    async with b.fabrica() as s:
        await EnrichmentService(s)._enrich_series_batch(cv, anilist, tebeosfera, 20, informe)
        await s.commit()
    return informe


async def serie(b: Banco, sid: UUID) -> Series:
    async with b.fabrica() as s:
        return (await s.execute(select(Series).where(Series.id == sid))).scalar_one()


class TestIdentidadElegida:

    async def test_el_control_una_serie_sin_identidad_si_se_empareja(self, banco):
        """Sin este control, las demás pruebas podrían pasar por no ejecutar nada."""
        sid = await sembrar(banco, "Flash")
        cv = Fuente()
        informe = await enriquecer(banco, cv=cv)
        assert cv.consultas == ["Flash"] and informe.series_enriched == ["Flash"]
        assert (await serie(banco, sid)).comic_vine_id == 999999

    @pytest.mark.parametrize("tradicion", [ComicTradition.AMERICAN, ComicTradition.BRITISH])
    async def test_una_serie_con_identidad_gcd_no_se_empareja_con_comic_vine(self, banco, tradicion):
        sid = await sembrar(banco, "Flash", tradicion, gcd_id=4120, metadata_source="gcd", locked_fields=["gcd_id"])
        cv = Fuente()
        informe = await enriquecer(banco, cv=cv)
        s = await serie(banco, sid)
        assert cv.consultas == [] and informe.series_enriched == [] and informe.series_no_match == []
        assert (s.gcd_id, s.comic_vine_id, s.metadata_source) == (4120, None, "gcd")
        assert s.enrichment_attempted_at is None            # ni siquiera se la considera: no consume el lote

    async def test_ni_una_de_manga_con_identidad_gcd_con_anilist(self, banco):
        sid = await sembrar(banco, "Berserk", ComicTradition.MANGA, gcd_id=77)
        anilist = Fuente()
        await enriquecer(banco, anilist=anilist)
        assert anilist.consultas == [] and (await serie(banco, sid)).anilist_id is None

    async def test_ni_un_tebeo_con_identidad_gcd_con_tebeosfera(self, banco):
        sid = await sembrar(banco, "Mortadelo", ComicTradition.TEBEO, gcd_id=78)
        teb = Fuente()
        await enriquecer(banco, tebeosfera=teb)
        assert teb.consultas == [] and (await serie(banco, sid)).tebeosfera_slug is None

    async def test_con_identidad_gcd_y_sin_ella_en_el_mismo_lote_solo_se_consulta_la_segunda(self, banco):
        con = await sembrar(banco, "Batman", gcd_id=5)
        sin = await sembrar(banco, "Superman")
        cv = Fuente()
        await enriquecer(banco, cv=cv)
        assert cv.consultas == ["Superman"]
        assert (await serie(banco, con)).comic_vine_id is None and (await serie(banco, sin)).comic_vine_id == 999999

    async def test_las_series_con_identidad_gcd_no_ocupan_el_lote(self, banco):
        """Se excluyen ANTES del límite: 25 series con GCD no dejan sin turno a una sin identidad."""
        for i in range(25):
            await sembrar(banco, f"Con identidad {i}", gcd_id=1000 + i)
        sin = await sembrar(banco, "Sin identidad")
        cv = Fuente()
        await enriquecer(banco, cv=cv)
        assert cv.consultas == ["Sin identidad"] and (await serie(banco, sin)).comic_vine_id == 999999

    @pytest.mark.parametrize("ids", [{"comic_vine_id": 1}, {"anilist_id": 2}, {"tebeosfera_slug": "x"},
                                     {"gcd_id": 3}, {"gcd_id": 3, "comic_vine_id": 1}])
    async def test_cualquier_identidad_elegida_la_excluye(self, banco, ids):
        sid = await sembrar(banco, "Flash", **ids)
        cv = Fuente()
        await enriquecer(banco, cv=cv)
        assert cv.consultas == []
        s = await serie(banco, sid)
        assert {k: getattr(s, k) for k in ids} == ids

    async def test_las_manuales_siguen_excluidas(self, banco):
        sid = await sembrar(banco, "Flash", metadata_source="manual")
        cv = Fuente()
        await enriquecer(banco, cv=cv)
        assert cv.consultas == [] and (await serie(banco, sid)).comic_vine_id is None


@pytest.mark.asyncio
async def test_generos_de_anilist_solo_rellenan_vacio_y_son_idempotentes(banco):
    from sqlalchemy import func

    from zascarr.models import Genre, series_genres
    sid = await sembrar(banco, "Berserk", ComicTradition.MANGA)
    await enriquecer(banco, anilist=Fuente(genres=["Action", "Adventure", "action"]))
    async with banco.fabrica() as s:
        filas = (await s.execute(
            select(Genre.name).join(series_genres, series_genres.c.genre_id == Genre.id)
            .where(series_genres.c.series_id == sid).order_by(Genre.name))).scalars().all()
    assert [n.casefold() for n in filas] == ["action", "adventure"]
    await enriquecer(banco, anilist=Fuente(genres=["Other"]))
    async with banco.fabrica() as s:
        total = (await s.execute(select(func.count()).select_from(series_genres)
                                 .where(series_genres.c.series_id == sid))).scalar_one()
    assert total == 2  # ya tenía géneros: no se sustituyen


@pytest.mark.asyncio
async def test_generos_respetan_locked_y_manual(banco):
    from zascarr.models import series_genres
    bloqueada = await sembrar(banco, "Berserk", ComicTradition.MANGA, locked_fields=["genres"])
    manual = await sembrar(banco, "Claymore", ComicTradition.MANGA, metadata_source="manual")
    await enriquecer(banco, anilist=Fuente(genres=["Action"]))
    async with banco.fabrica() as s:
        for sid in (bloqueada, manual):
            n = (await s.execute(select(series_genres.c.genre_id)
                                 .where(series_genres.c.series_id == sid))).first()
            assert n is None


@pytest.mark.asyncio
async def test_anilist_aporta_generos_y_tebeosfera_no_inventa(banco):
    from zascarr.models import series_genres
    manga = await sembrar(banco, "Berserk", ComicTradition.MANGA)
    tebeo = await sembrar(banco, "Mortadelo", ComicTradition.TEBEO)
    await enriquecer(banco, anilist=Fuente(genres=["Action"]), tebeosfera=Fuente(genres=["Inventado"]))
    async with banco.fabrica() as s:
        manga_n = (await s.execute(select(series_genres.c.genre_id)
                                   .where(series_genres.c.series_id == manga))).first()
        tebeo_n = (await s.execute(select(series_genres.c.genre_id)
                                   .where(series_genres.c.series_id == tebeo))).first()
    assert manga_n is not None and tebeo_n is None


@pytest.mark.asyncio
async def test_personajes_del_numero_solo_rellenan_vacio_y_respetan_locked(banco):
    from zascarr.models import Character, Issue, issue_characters
    sid = await sembrar(banco, "Flash", comic_vine_id=123)
    iid = uuid4()
    async with banco.fabrica() as s:
        s.add(Issue(id=iid, series_id=sid, issue_number="1"))
        await s.commit()
    cv = Fuente(characters=["Barry Allen", "Iris West"])
    informe = EnrichmentReport()
    async with banco.fabrica() as s:
        await EnrichmentService(s)._enrich_issues_batch(cv, 20, informe)
        await s.commit()
    async with banco.fabrica() as s:
        nombres = (await s.execute(
            select(Character.name).join(issue_characters, issue_characters.c.character_id == Character.id)
            .where(issue_characters.c.issue_id == iid).order_by(Character.name))).scalars().all()
    assert nombres == ["Barry Allen", "Iris West"]
    # Idempotente: una segunda pasada no duplica.
    async with banco.fabrica() as s:
        await EnrichmentService(s)._enrich_issues_batch(Fuente(characters=["Otro"]), 20, EnrichmentReport())
        await s.commit()
    async with banco.fabrica() as s:
        total = (await s.execute(select(issue_characters.c.character_id)
                                 .where(issue_characters.c.issue_id == iid))).all()
    assert len(total) == 2


class FuenteConDetalle:
    """AniList/CV falsos con detalle por id, para el backfill."""

    def __init__(self, *, generos=None, personajes=None):
        self.generos = list(generos or [])
        self.personajes = list(personajes or [])
        self.pedidos: list[int] = []

    async def get_manga(self, anilist_id):
        self.pedidos.append(int(anilist_id))
        return SimpleNamespace(genres=list(self.generos))

    async def get_issue_detail(self, cv_id):
        self.pedidos.append(int(cv_id))
        return {"character_credits": [{"name": n} for n in self.personajes]}


@pytest.mark.asyncio
async def test_backfill_anilist_rellena_generos_vacios_es_idempotente_y_acotado(banco):
    from zascarr.models import series_genres
    sid = await sembrar(banco, "Berserk", ComicTradition.MANGA, anilist_id=55)
    otra = await sembrar(banco, "Claymore", ComicTradition.MANGA, anilist_id=56)
    fuente = FuenteConDetalle(generos=["Action"])
    async with banco.fabrica() as s:
        servicio = EnrichmentService(s)
        await servicio._backfill_generos_anilist(fuente, 1, EnrichmentReport())
        await s.commit()
    assert len(fuente.pedidos) == 1
    async with banco.fabrica() as s:
        n = (await s.execute(select(series_genres.c.genre_id)
                             .where(series_genres.c.series_id == sid))).first()
        m = (await s.execute(select(series_genres.c.genre_id)
                             .where(series_genres.c.series_id == otra))).first()
    assert n is not None and m is None
    # Segunda pasada: la primera ya está marcada y la otra se rellena una sola vez.
    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_generos_anilist(fuente, 10, EnrichmentReport())
        await s.commit()
    assert fuente.pedidos == [55, 56]
    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_generos_anilist(fuente, 10, EnrichmentReport())
        await s.commit()
    assert fuente.pedidos == [55, 56]


@pytest.mark.asyncio
async def test_backfill_personajes_cv_rellena_vacios_es_idempotente(banco):
    from zascarr.models import Issue, issue_characters
    sid = await sembrar(banco, "Flash", comic_vine_id=123)
    iid = uuid4()
    async with banco.fabrica() as s:
        s.add(Issue(id=iid, series_id=sid, issue_number="1", comic_vine_id=999))
        await s.commit()
    fuente = FuenteConDetalle(personajes=["Barry Allen"])
    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_personajes_cv(fuente, 10, EnrichmentReport())
        await s.commit()
    from zascarr.models import Character
    async with banco.fabrica() as s:
        nombres = (await s.execute(
            select(Character.name).join(issue_characters, issue_characters.c.character_id == Character.id)
            .where(issue_characters.c.issue_id == iid))).scalars().all()
    assert nombres == ["Barry Allen"]
    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_personajes_cv(fuente, 10, EnrichmentReport())
        await s.commit()
    assert fuente.pedidos == [999]


@pytest.mark.asyncio
async def test_backfill_respeta_manual_y_locked(banco):
    from zascarr.models import Issue, series_genres
    bloqueada = await sembrar(banco, "Berserk", ComicTradition.MANGA, anilist_id=77,
                              locked_fields=["genres"])
    manual = await sembrar(banco, "Claymore", ComicTradition.MANGA, anilist_id=78,
                           metadata_source="manual")
    sid = await sembrar(banco, "Flash", comic_vine_id=123)
    issue_locked = uuid4()
    issue_manual = uuid4()
    async with banco.fabrica() as s:
        s.add(Issue(id=issue_locked, series_id=sid, issue_number="1", comic_vine_id=1,
                    locked_fields=["characters"]))
        s.add(Issue(id=issue_manual, series_id=sid, issue_number="2", comic_vine_id=2,
                    metadata_source="manual"))
        await s.commit()
    fuente = FuenteConDetalle(generos=["Action"], personajes=["Barry Allen"])
    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_generos_anilist(fuente, 10, EnrichmentReport())
        await EnrichmentService(s)._backfill_personajes_cv(fuente, 10, EnrichmentReport())
        await s.commit()
    assert fuente.pedidos == []
    async with banco.fabrica() as s:
        for sid_ in (bloqueada, manual):
            n = (await s.execute(select(series_genres.c.genre_id)
                                 .where(series_genres.c.series_id == sid_))).first()
            assert n is None
