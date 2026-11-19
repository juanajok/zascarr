"""CCM Fase 1: tipos, normalizadores, adaptadores y recolector (sin red/BD)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from zascarr.core.consolidacion.normalizadores import (
    normalizar_comic_vine_serie,
    normalizar_gcd_serie,
    normalizar_tebeosfera_serie,
)
from zascarr.core.consolidacion.tipos import (
    EstadoFetch,
    FichaRecolectada,
    ResultadoFetch,
    hash_payload,
)
from zascarr.services.consolidacion.adaptadores import (
    AdaptadorComicVine,
    AdaptadorGCD,
    AdaptadorTebeosfera,
)
from zascarr.services.consolidacion.recolector import Recolector


class _ClienteCV:
    async def get_volume(self, volume_id):
        return SimpleNamespace(
            cv_id=volume_id, name="Batman", publisher="DC Comics",
            start_year=1940, count_of_issues=1000, raw={},
        )


class _ClienteTebeosfera:
    async def get_collection(self, slug):
        return SimpleNamespace(
            slug=slug, titulo="Patrulla-X", editorial="Fórum", sello="Forum",
            anio=1985, anio_fin=None, pais="ES", idioma="es",
            url_ficha="https://example.test/patrulla-x", numeros_slugs=(),
        )


class _ClienteGCD:
    async def get_series(self, gcd_id):
        return SimpleNamespace(
            gcd_id=gcd_id, name="Batman", year_began=1940, year_ended=None,
            country="US", language="en", issue_count=1000,
            publishing_format="comic book", binding="saddle-stitched",
            publisher="https://www.comics.org/publisher/1/",
        )


def test_normalizador_cv_no_inventa_campos_ausentes():
    datos = normalizar_comic_vine_serie(SimpleNamespace(
        name="Batman", publisher=None, start_year=1940, count_of_issues=None, raw={}))
    assert datos["edition_scope"] == {"title": "Batman", "start_year": 1940}
    assert datos["work_scope"] == {}


def test_normalizadores_tebeosfera_y_gcd_usan_solo_lo_declarado():
    tebeo = normalizar_tebeosfera_serie(SimpleNamespace(
        titulo="Patrulla-X", editorial="Fórum", sello="Forum", anio=1985,
        anio_fin=None, pais="ES", idioma="es"))
    assert tebeo["edition_scope"]["country"] == "ES"
    assert "end_year" not in tebeo["edition_scope"] and "total_issues" not in tebeo["edition_scope"]
    gcd = normalizar_gcd_serie(SimpleNamespace(
        name="Batman", year_began=1940, year_ended=2011, country="US",
        language="en", issue_count=713, publishing_format="comic book",
        binding="saddle-stitched"))
    assert gcd["edition_scope"] == {
        "title": "Batman", "start_year": 1940, "end_year": 2011,
        "country": "US", "language": "en", "total_issues": 713,
    }


@pytest.mark.asyncio
async def test_adaptador_cv_devuelve_ficha_y_no_modificado_por_hash():
    adaptador = AdaptadorComicVine(_ClienteCV())
    primero = await adaptador.fetch_serie("4050")
    assert primero.estado is EstadoFetch.OK and primero.ficha is not None
    assert primero.ficha.normalizado["edition_scope"]["title"] == "Batman"
    assert primero.ficha.raw_acotado["id"] == 4050
    segundo = await adaptador.fetch_serie("4050", hash_previo=primero.ficha.payload_hash)
    assert segundo.estado is EstadoFetch.NO_MODIFICADO


@pytest.mark.asyncio
async def test_adaptadores_tebeosfera_y_gcd_por_id():
    tebeo = await AdaptadorTebeosfera(_ClienteTebeosfera()).fetch_serie("patrulla_x")
    assert tebeo.ficha is not None
    assert tebeo.ficha.url == "https://example.test/patrulla-x"
    assert "CC BY-SA" not in (tebeo.ficha.licencia or "")
    gcd = await AdaptadorGCD(_ClienteGCD()).fetch_serie("1")
    assert gcd.ficha is not None
    assert "CC BY-SA" in (gcd.ficha.licencia or "")
    assert gcd.ficha.normalizado["edition_scope"]["country"] == "US"


class _AdaptadorFalso:
    nombre = "comic_vine"
    capacidades_serie = frozenset({"title"})

    def __init__(self, resultado):
        self.resultado = resultado
        self.llamadas = []

    async def fetch_serie(self, external_id, *, hash_previo=None):
        self.llamadas.append((external_id, hash_previo))
        return self.resultado


class _RecolectorPrueba(Recolector):
    def __init__(self, adaptadores):
        super().__init__(db=None, adaptadores=adaptadores)
        self.guardadas = []

    async def _hash_previo(self, series_id, fuente, external_id):
        return None

    async def _guardar(self, series_id, ficha):
        self.guardadas.append((series_id, ficha.fuente, ficha.external_id))


def _ficha() -> FichaRecolectada:
    return FichaRecolectada(
        fuente="comic_vine", entidad="series", external_id="1",
        url=None, licencia="x", raw_acotado={"name": "Batman"},
        normalizado={"edition_scope": {"title": "Batman"}},
        normalizer_version=1, payload_hash=hash_payload({"x": 1}),
        observado_en=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_recolector_guarda_solo_evidencia_y_no_muta_la_serie():
    serie = SimpleNamespace(id="s-1", comic_vine_id=1, tebeosfera_slug=None, gcd_id=None)
    adaptador = _AdaptadorFalso(ResultadoFetch(EstadoFetch.OK, _ficha()))
    recolector = _RecolectorPrueba({"comic_vine": adaptador})
    informe = await recolector.recolectar_serie(serie)
    assert informe.guardados == 1
    assert recolector.guardadas == [("s-1", "comic_vine", "1")]
    assert adaptador.llamadas == [("1", None)]
    assert serie.comic_vine_id == 1 and not hasattr(serie, "title")


@pytest.mark.asyncio
async def test_recolector_ignora_fuentes_sin_id_y_errores():
    serie = SimpleNamespace(id="s-1", comic_vine_id=None, tebeosfera_slug=None, gcd_id=None)
    adaptador = _AdaptadorFalso(ResultadoFetch(EstadoFetch.ERROR_RED))
    recolector = _RecolectorPrueba({"comic_vine": adaptador})
    assert (await recolector.recolectar_serie(serie)).resultados == []
    assert adaptador.llamadas == []
