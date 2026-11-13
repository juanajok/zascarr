# ruff: noqa: E501
"""ETQ4 (#697): AniList aporta etiquetas de tema con `weight=rank` sin pisar las manuales.

Dos niveles: unitarias del parseo y del mapeo del match (sin BD); y pruebas
sobre Postgres real para la escritura en `series_tags` y el backfill (se
saltan sin `TEST_DATABASE_URL`). Las fuentes se simulan: ninguna prueba toca
la red.
"""
from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text

from tests._pg import bd_efimera_sync, migrar_a_head
from tests.test_revision_carpetas_pg import Banco
from zascarr.models import ComicTradition, Series, Tag, series_tags
from zascarr.services import anilist
from zascarr.services.anilist import AniListResult, AniListTag, _parse_media, _parse_tags
from zascarr.services.enricher import EnrichmentReport, EnrichmentService

URL = os.environ.get("TEST_DATABASE_URL")
requiere_bd = pytest.mark.skipif(not URL, reason="requiere TEST_DATABASE_URL (Postgres real)")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Parseo de tags de AniList (sin red)
# ═══════════════════════════════════════════════════════════════════════════════

class TestParseTags:

    def test_nombre_y_rank(self):
        assert _parse_tags([{"name": "Space Opera", "rank": 88}]) == [
            AniListTag("Space Opera", 88)
        ]

    def test_dedupe_por_caja_y_conserva_el_primero(self):
        assert _parse_tags([{"name": "Noir", "rank": 90},
                            {"name": "noir", "rank": 10}]) == [AniListTag("Noir", 90)]

    def test_rank_fuera_de_rango_se_acota(self):
        tags = _parse_tags([{"name": "A", "rank": 150}, {"name": "B", "rank": -5}])
        assert [t.rank for t in tags] == [100, 0]

    def test_sin_rank_o_no_numerico_queda_none(self):
        tags = _parse_tags([{"name": "A"}, {"name": "B", "rank": "x"},
                            {"name": "C", "rank": None}])
        assert [t.rank for t in tags] == [None, None, None]

    def test_ignora_vacios_y_no_dict(self):
        assert _parse_tags([None, "x", {"rank": 5}, {"name": "   "}]) == []
        assert _parse_tags(None) == []

    def test_parse_media_expone_los_tags(self):
        resultado = _parse_media({"id": 7, "tags": [{"name": "Isekai", "rank": 70}]})
        assert resultado.tags == [AniListTag("Isekai", 70)]


class TestConsultasAniList:

    def test_la_busqueda_y_el_detalle_piden_los_tags_en_la_misma_peticion(self):
        """Sin llamadas extra: `tags { name rank }` viaja en la query que ya existía."""
        assert "tags { name rank }" in anilist._SEARCH_QUERY
        assert "tags { name rank }" in anilist._DETAIL_QUERY


class TestFindAniListMatch:

    @pytest.mark.asyncio
    async def test_los_tags_del_match_llegan_a_series_match(self):
        cliente = AsyncMock()
        cliente.search_manga.return_value = [
            AniListResult(anilist_id=1, title_romaji="Berserk",
                          tags=[AniListTag("Dark Fantasy", 95)]),
        ]
        servicio = EnrichmentService(db=MagicMock())
        serie = Series(id=uuid4(), title="Berserk", tradition=ComicTradition.MANGA)

        match = await servicio._find_anilist_match(cliente, serie)

        assert match is not None
        assert match.tags == [AniListTag("Dark Fantasy", 95)]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Escritura en series_tags (Postgres real, fuentes simuladas)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def url_bd():
    with bd_efimera_sync(URL) as url:
        migrar_a_head(url)
        yield url


@pytest.fixture
async def banco(url_bd):
    b = Banco(url_bd)
    await b.limpiar()
    # `Banco.limpiar` vacía series (y por CASCADE series_tags), pero no `tags`:
    # sin esto una etiqueta de una prueba anterior aparecería en la siguiente.
    async with b.motor.begin() as conexion:
        await conexion.execute(text("TRUNCATE tags CASCADE"))
    yield b
    await b.cerrar()


async def sembrar(b: Banco, titulo: str, tradicion=ComicTradition.MANGA, **campos) -> UUID:
    sid = uuid4()
    async with b.fabrica() as s:
        s.add(Series(id=sid, title=titulo, tradition=tradicion, **campos))
        await s.commit()
    return sid


async def filas(b: Banco, sid: UUID) -> list[tuple]:
    """(name, namespace, source, weight, oculta) de las etiquetas de la serie."""
    async with b.fabrica() as s:
        resultado = await s.execute(
            select(Tag.name, Tag.namespace, series_tags.c.source,
                   series_tags.c.weight, series_tags.c.oculta)
            .join(series_tags, series_tags.c.tag_id == Tag.id)
            .where(series_tags.c.series_id == sid)
            .order_by(Tag.name)
        )
        return [tuple(fila) for fila in resultado.all()]


async def aplicar(b: Banco, sid: UUID, tags: list[AniListTag]) -> int:
    async with b.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
        creadas = await EnrichmentService(s)._aplicar_tags(serie, tags)
        await s.commit()
    return creadas


@requiere_bd
@pytest.mark.asyncio
async def test_aplicar_tags_escribe_source_anilist_y_weight_rank(banco):
    sid = await sembrar(banco, "Berserk")

    creadas = await aplicar(banco, sid, [AniListTag("Dark Fantasy", 95),
                                         AniListTag("Gore", 60)])

    assert creadas == 2
    assert await filas(banco, sid) == [
        ("Dark Fantasy", "etiqueta", "anilist", 95, False),
        ("Gore", "etiqueta", "anilist", 60, False),
    ]


@requiere_bd
@pytest.mark.asyncio
async def test_aplicar_tags_es_idempotente(banco):
    sid = await sembrar(banco, "Berserk")

    assert await aplicar(banco, sid, [AniListTag("Noir", 80)]) == 1
    assert await aplicar(banco, sid, [AniListTag("Noir", 80)]) == 0
    assert await filas(banco, sid) == [("Noir", "etiqueta", "anilist", 80, False)]


@requiere_bd
@pytest.mark.asyncio
async def test_manual_gana_y_no_se_duplica(banco):
    sid = await sembrar(banco, "Berserk")
    async with banco.fabrica() as s:
        tag = Tag(name="Noir", namespace="etiqueta")
        s.add(tag)
        await s.flush()
        await s.execute(series_tags.insert().values(
            series_id=sid, tag_id=tag.id, source="manual"))
        await s.commit()

    assert await aplicar(banco, sid, [AniListTag("noir", 90)]) == 0
    assert await filas(banco, sid) == [("Noir", "etiqueta", "manual", None, False)]


@requiere_bd
@pytest.mark.asyncio
async def test_una_fila_oculta_no_resucita(banco):
    sid = await sembrar(banco, "Berserk")
    async with banco.fabrica() as s:
        tag = Tag(name="Noir", namespace="etiqueta")
        s.add(tag)
        await s.flush()
        await s.execute(series_tags.insert().values(
            series_id=sid, tag_id=tag.id, source="anilist", weight=50, oculta=True))
        await s.commit()

    assert await aplicar(banco, sid, [AniListTag("Noir", 99)]) == 0
    assert await filas(banco, sid) == [("Noir", "etiqueta", "anilist", 50, True)]


@requiere_bd
@pytest.mark.asyncio
async def test_locked_fields_tags_no_escribe(banco):
    sid = await sembrar(banco, "Berserk", locked_fields=["tags"])

    assert await aplicar(banco, sid, [AniListTag("Noir", 90)]) == 0
    assert await filas(banco, sid) == []


@requiere_bd
@pytest.mark.asyncio
async def test_sin_rank_el_peso_es_null(banco):
    sid = await sembrar(banco, "Berserk")

    assert await aplicar(banco, sid, [AniListTag("Mystery", None)]) == 1
    assert await filas(banco, sid) == [("Mystery", "etiqueta", "anilist", None, False)]


@requiere_bd
@pytest.mark.asyncio
async def test_los_nombres_invalidos_se_ignoran_y_los_validos_entran(banco):
    sid = await sembrar(banco, "Berserk")

    creadas = await aplicar(banco, sid, [AniListTag("a,b", 10), AniListTag("x" * 65, 20),
                                         AniListTag("   ", 30), AniListTag("Noir", 40)])

    assert creadas == 1
    assert await filas(banco, sid) == [("Noir", "etiqueta", "anilist", 40, False)]


class FuenteManga:
    """AniList falsa que siempre devuelve el mismo resultado de búsqueda."""

    def __init__(self, resultado):
        self.resultado = resultado
        self.consultas: list[str] = []

    async def search_manga(self, titulo, limit=10):
        self.consultas.append(titulo)
        return [self.resultado]


@requiere_bd
@pytest.mark.asyncio
async def test_el_match_nuevo_aplica_los_tags_en_la_misma_pasada(banco):
    sid = await sembrar(banco, "Berserk")
    fuente = FuenteManga(SimpleNamespace(
        anilist_id=1, title_romaji="Berserk", title_english=None, start_year=None,
        description=None, cover_url=None, chapters=None, genres=[],
        tags=[AniListTag("Dark Fantasy", 95)],
    ))

    async with banco.fabrica() as s:
        await EnrichmentService(s)._enrich_series_batch(
            None, fuente, None, 20, EnrichmentReport())
        await s.commit()

    assert fuente.consultas == ["Berserk"]
    assert await filas(banco, sid) == [("Dark Fantasy", "etiqueta", "anilist", 95, False)]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Backfill de series ya identificadas con AniList
# ═══════════════════════════════════════════════════════════════════════════════

class FuenteDetalle:
    """AniList falsa con detalle por id, para el backfill."""

    def __init__(self, tags=None, *, falla=False):
        self.tags = list(tags or [])
        self.falla = falla
        self.pedidos: list[int] = []

    async def get_manga(self, anilist_id):
        self.pedidos.append(int(anilist_id))
        if self.falla:
            raise RuntimeError("red caída")
        return SimpleNamespace(tags=list(self.tags))


@requiere_bd
@pytest.mark.asyncio
async def test_backfill_aplica_tags_y_marca_el_intento(banco):
    sid = await sembrar(banco, "Berserk", anilist_id=55)
    fuente = FuenteDetalle([AniListTag("Dark Fantasy", 95)])
    informe = EnrichmentReport()

    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_tags_anilist(fuente, 10, informe)
        await s.commit()

    assert fuente.pedidos == [55]
    assert await filas(banco, sid) == [("Dark Fantasy", "etiqueta", "anilist", 95, False)]

    # La marca `etq4_tags_intentado` evita repetir la petición en el siguiente ciclo.
    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_tags_anilist(fuente, 10, informe)
        await s.commit()
    assert fuente.pedidos == [55]


@requiere_bd
@pytest.mark.asyncio
async def test_backfill_respeta_manual_y_locked(banco):
    manual = await sembrar(banco, "Claymore", anilist_id=56, metadata_source="manual")
    bloqueada = await sembrar(banco, "Berserk", anilist_id=57, locked_fields=["tags"])
    fuente = FuenteDetalle([AniListTag("Noir", 80)])

    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_tags_anilist(fuente, 10, EnrichmentReport())
        await s.commit()

    assert fuente.pedidos == []
    assert await filas(banco, manual) == []
    assert await filas(banco, bloqueada) == []


@requiere_bd
@pytest.mark.asyncio
async def test_backfill_esta_acotado_por_limit(banco):
    await sembrar(banco, "Berserk", anilist_id=55)
    await sembrar(banco, "Claymore", anilist_id=56)
    fuente = FuenteDetalle([AniListTag("Noir", 80)])

    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_tags_anilist(fuente, 1, EnrichmentReport())
        await s.commit()

    assert len(fuente.pedidos) == 1


@requiere_bd
@pytest.mark.asyncio
async def test_un_fallo_no_marca_el_intento_para_poder_reintentar(banco):
    sid = await sembrar(banco, "Berserk", anilist_id=55)
    fuente = FuenteDetalle(falla=True)
    informe = EnrichmentReport()

    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_tags_anilist(fuente, 10, informe)
        await s.commit()

    assert informe.errors == ["serie Berserk: error pidiendo etiquetas"]
    assert await filas(banco, sid) == []
    async with banco.fabrica() as s:
        serie = (await s.execute(select(Series).where(Series.id == sid))).scalar_one()
    assert "etq4_tags_intentado" not in (serie.metadata_ or {})


@requiere_bd
@pytest.mark.asyncio
async def test_sin_cliente_anilist_el_backfill_no_hace_nada(banco):
    await sembrar(banco, "Berserk", anilist_id=55)

    async with banco.fabrica() as s:
        await EnrichmentService(s)._backfill_tags_anilist(None, 10, EnrichmentReport())
        await s.commit()
