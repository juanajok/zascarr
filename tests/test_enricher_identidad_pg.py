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

    def __init__(self):
        self.consultas: list[str] = []

    async def search_series(self, titulo, limit=10):
        self.consultas.append(titulo)
        return [SimpleNamespace(name=titulo, cv_id=999999, start_year=None, description="d",
                                image_url=None, count_of_issues=None, slug="slug_nuevo", title=titulo,
                                kind="collection", cover_url=None, site_url=None)]

    async def search_manga(self, titulo, limit=10):
        self.consultas.append(titulo)
        return [SimpleNamespace(title_romaji=titulo, title_english=None, anilist_id=888888, start_year=None,
                                description="d", cover_url=None, chapters=None)]


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
