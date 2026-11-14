"""SCR7: relleno de huecos por id (lógica pura + enricher con clientes inyectados)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from zascarr.utils.peticiones import ErrorDePeticion

AHORA = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _serie(**kw):
    base = dict(id=uuid4(), title="Batman", description=None, start_year=None,
                end_year=None, comic_vine_id=None, anilist_id=None,
                tebeosfera_slug=None, gcd_id=None, metron_id=None,
                open_library_id=None, fandom_dc_slug=None, fandom_marvel_slug=None,
                metadata_source="gcd", tradition="american", metadata_={},
                locked_fields=[], cover_url="portada.jpg", total_issues=12)
    base.update(kw)
    return SimpleNamespace(**base)


def _ficha_gcd():
    from zascarr.services.gcd import GCDSerie
    return GCDSerie(gcd_id=77, name="Batman", year_began=1940, year_ended=2011)


def _ficha_metron():
    from zascarr.services.metron import MetronResult
    return MetronResult(metron_id=88, name="Batman", year_began=1940,
                        year_ended=2011, descripcion="Sinopsis de Metron",
                        site_url="https://metron.cloud/series/88/")


def _ficha_ol():
    from zascarr.services.open_library import OpenLibraryResult
    return OpenLibraryResult(work_id="OL1W", title="Batman", start_year=1939,
                             description="Sinopsis de Open Library")


class TestAplicarRelleno:

    def test_ac_01_gcd_solo_rellena_anios_y_no_toca_el_resto(self):
        from zascarr.services.relleno_huecos import aplicar_relleno

        serie = _serie(metadata_source="gcd")
        campos = aplicar_relleno(serie, "gcd", _ficha_gcd(), AHORA)
        assert campos == ["start_year", "end_year"]
        assert (serie.start_year, serie.end_year) == (1940, 2011)
        assert serie.title == "Batman" and serie.cover_url == "portada.jpg"
        assert serie.total_issues == 12 and serie.metadata_source == "gcd"

    def test_ac_02_metron_rellena_descripcion_y_anios_sin_portada(self):
        from zascarr.services.relleno_huecos import aplicar_relleno

        serie = _serie(metadata_source="metron")
        campos = aplicar_relleno(serie, "metron", _ficha_metron(), AHORA)
        assert campos == ["description", "start_year", "end_year"]
        assert serie.description == "Sinopsis de Metron"
        assert serie.cover_url == "portada.jpg"      # nunca se toca
        assert serie.metadata_["relleno"]["metron"]["url_ficha"] == (
            "https://metron.cloud/series/88/")

    def test_ac_03_open_library_rellena_descripcion_y_anio(self):
        from zascarr.services.relleno_huecos import aplicar_relleno

        serie = _serie(metadata_source="open_library")
        campos = aplicar_relleno(serie, "open_library", _ficha_ol(), AHORA)
        assert campos == ["description", "start_year"]
        assert serie.description == "Sinopsis de Open Library"
        assert serie.start_year == 1939 and serie.end_year is None
        assert serie.metadata_["relleno"]["open_library"]["id"] == "OL1W"

    def test_ac_04_no_pisa_campos_llenos_ni_bloqueados(self):
        from zascarr.services.relleno_huecos import aplicar_relleno

        serie = _serie(description="mía", start_year=2000, end_year=2010,
                       locked_fields=["description"])
        assert aplicar_relleno(serie, "metron", _ficha_metron(), AHORA) == []
        assert serie.description == "mía" and serie.start_year == 2000
        assert serie.metadata_source == "gcd"

    def test_ac_04_nunca_escribe_campos_prohibidos(self):
        from zascarr.services.relleno_huecos import aplicar_relleno

        serie = _serie(title="Original", gcd_id=None, metadata_source="gcd",
                       cover_url="portada.jpg", total_issues=12)
        ficha = SimpleNamespace(gcd_id=77, year_began=1900, year_ended=1910,
                                title="OTRO", cover_url="otra.jpg", total_issues=99,
                                metadata_source="otra")
        aplicar_relleno(serie, "gcd", ficha, AHORA)
        assert serie.title == "Original" and serie.gcd_id is None
        assert serie.metadata_source == "gcd"
        assert serie.cover_url == "portada.jpg" and serie.total_issues == 12

    def test_metadata_se_escribe_con_dict_nuevo(self):
        from zascarr.services.relleno_huecos import aplicar_relleno

        original = {"otra": True}
        serie = _serie(metadata_=original)
        aplicar_relleno(serie, "gcd", _ficha_gcd(), AHORA)
        assert serie.metadata_ is not original
        assert original == {"otra": True}            # no mutación in-place
        assert serie.metadata_["otra"] is True

    def test_ttl_de_treinta_dias(self):
        from zascarr.services.relleno_huecos import aplicar_relleno, ttl_vigente

        serie = _serie()
        aplicar_relleno(serie, "gcd", None, AHORA)   # 404
        assert serie.metadata_["relleno"]["gcd"]["campos"] == []
        assert ttl_vigente(serie, "gcd", AHORA + timedelta(days=29))
        assert not ttl_vigente(serie, "gcd", AHORA + timedelta(days=31))


class _Sesion:
    def __init__(self, filas):
        self._filas = list(filas)
        self.flush = AsyncMock()
        self.consultas = 0

    async def execute(self, _stmt):
        self.consultas += 1
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._filas))


class _Cliente:
    def __init__(self, ficha=None, *, error=None):
        self.ficha = ficha
        self.error = error
        self.llamadas: list[int | str] = []

    async def get_series_por_id(self, ident):
        self.llamadas.append(ident)
        if self.error is not None:
            raise self.error
        return self.ficha

    async def get_work(self, ident):
        self.llamadas.append(ident)
        if self.error is not None:
            raise self.error
        return self.ficha


def _servicio(filas):
    from zascarr.services.enricher import EnrichmentService
    return EnrichmentService(db=_Sesion(filas))


async def test_ac_01_a_03_el_enricher_rellena_por_id_y_solo_huecos():
    serie = _serie(gcd_id=77, description="propia")
    servicio = _servicio([serie])
    gcd = _Cliente(_ficha_gcd())
    await servicio._enrich_huecos_por_id(gcd, None, None, 10, servicio._report()
                                         if hasattr(servicio, "_report") else
                                         __import__("zascarr.services.enricher",
                                                    fromlist=["EnrichmentReport"]).EnrichmentReport())
    assert gcd.llamadas == [77]
    assert serie.start_year == 1940 and serie.end_year == 2011
    assert serie.description == "propia"            # solo huecos
    assert servicio.db.flush.await_count >= 1


async def test_ac_05_404_marca_ttl_y_transitorio_no():
    from zascarr.services.enricher import EnrichmentReport

    sin_datos = _serie(gcd_id=1)
    servicio = _servicio([sin_datos])
    await servicio._enrich_huecos_por_id(_Cliente(None), None, None, 10,
                                         EnrichmentReport())
    assert sin_datos.metadata_["relleno"]["gcd"]["campos"] == []

    transitorio = _serie(metron_id=2)
    servicio = _servicio([transitorio])
    await servicio._enrich_huecos_por_id(
        None, _Cliente(error=ErrorDePeticion("red")), None, 10, EnrichmentReport())
    assert "relleno" not in (transitorio.metadata_ or {})

    # Segunda pasada: el TTL del 404 evita la petición; el transitorio sí se reintenta.
    gcd = _Cliente(_ficha_gcd())
    servicio = _servicio([sin_datos, transitorio])
    metron = _Cliente(_ficha_metron())
    await servicio._enrich_huecos_por_id(gcd, metron, None, 10, EnrichmentReport())
    assert gcd.llamadas == [] and metron.llamadas == [2]


async def test_ac_06_idempotente_tras_rellenar():
    from zascarr.services.enricher import EnrichmentReport

    serie = _serie(gcd_id=1, metron_id=2, open_library_id="OL1W")
    servicio = _servicio([serie])
    metron = _Cliente(_ficha_metron())
    await servicio._enrich_huecos_por_id(None, metron, None, 10, EnrichmentReport())
    assert metron.llamadas == [2] and serie.description == "Sinopsis de Metron"
    # Ya no quedan huecos que Metron cubra: segunda pasada sin peticiones.
    await servicio._enrich_huecos_por_id(None, metron, None, 10, EnrichmentReport())
    assert metron.llamadas == [2]


async def test_ac_07_orden_metron_open_library_gcd_y_parada():
    from zascarr.services.enricher import EnrichmentReport

    serie = _serie(gcd_id=1, metron_id=2, open_library_id="OL1W")
    orden: list[str] = []

    class ClienteOrden(_Cliente):
        def __init__(self, ficha, rol):
            super().__init__(ficha)
            self.rol = rol

        async def get_series_por_id(self, ident):
            orden.append(self.rol)
            return await super().get_series_por_id(ident)

        async def get_work(self, ident):
            orden.append(self.rol)
            return await super().get_work(ident)

    metron = ClienteOrden(_ficha_metron(), "metron")
    ol = ClienteOrden(_ficha_ol(), "open_library")
    gcd = ClienteOrden(_ficha_gcd(), "gcd")
    servicio = _servicio([serie])
    await servicio._enrich_huecos_por_id(gcd, metron, ol, 10, EnrichmentReport())
    assert orden == ["metron"]                     # Metron cubrió todos los huecos
    # Con Metron devolviendo solo años, pasa a OL y luego GCD.
    serie2 = _serie(gcd_id=1, metron_id=2, open_library_id="OL1W")
    orden.clear()
    metron2 = ClienteOrden(SimpleNamespace(metron_id=2, year_began=1990,
                                           year_ended=None, descripcion=None,
                                           site_url=None), "metron")
    servicio = _servicio([serie2])
    await servicio._enrich_huecos_por_id(gcd, metron2, ol, 10, EnrichmentReport())
    assert orden[0] == "metron" and "open_library" in orden
    # GCD nunca adelanta a OL.
    assert orden.index("metron") < orden.index("open_library")


async def test_ac_07_tradiciones_y_topes():
    from zascarr.services.enricher import EnrichmentReport

    manga = _serie(gcd_id=1, metron_id=2, tradition="manga")
    gcd = _Cliente(_ficha_gcd())
    metron = _Cliente(_ficha_metron())
    servicio = _servicio([manga])
    await servicio._enrich_huecos_por_id(gcd, metron, None, 10, EnrichmentReport())
    assert gcd.llamadas == [] and metron.llamadas == []

    series = [_serie(gcd_id=i) for i in range(1, 9)]
    gcd = _Cliente(_ficha_gcd())
    servicio = _servicio(series)
    await servicio._enrich_huecos_por_id(gcd, None, None, 20, EnrichmentReport())
    assert len(gcd.llamadas) == 5                  # tope por fuente y ciclo


async def test_ac_08_sin_clientes_no_consulta_la_bd():
    from zascarr.services.enricher import EnrichmentReport

    servicio = _servicio([_serie(gcd_id=1)])
    await servicio._enrich_huecos_por_id(None, None, None, 10, EnrichmentReport())
    assert servicio.db.consultas == 0

    from zascarr.config import Settings
    ajustes = Settings(_env_file=None)
    stack = SimpleNamespace(enter_async_context=AsyncMock())
    assert await servicio._cliente_metron(stack, ajustes) is None   # sin token
    assert stack.enter_async_context.await_count == 0


def test_ac_11_el_primario_excluye_metron_y_open_library():
    from zascarr.services.enricher import puede_enlazarse_con_comic_vine

    base = dict(comic_vine_id=None, anilist_id=None, tebeosfera_slug=None,
                gcd_id=None, metadata_source="metron", tradition="american")
    serie = SimpleNamespace(**base, metron_id=5, open_library_id=None)
    assert not puede_enlazarse_con_comic_vine(serie, True)
    serie = SimpleNamespace(**base, metron_id=None, open_library_id="OL1W")
    assert not puede_enlazarse_con_comic_vine(serie, True)
    serie = SimpleNamespace(**base, metron_id=None, open_library_id=None)
    assert puede_enlazarse_con_comic_vine(serie, True)


# ── Clientes por id con MockTransport (AC-01…03/05) ───────────────────────────────────────

import httpx  # noqa: E402

from zascarr.utils.cortesia import PoliticaFuente  # noqa: E402

AJUSTES_CLIENTES = SimpleNamespace(
    gcd_enabled=True, gcd_rate_limit=0.0, metron_enabled=True, metron_token="tok",
    metron_rate_limit=0.0, open_library_enabled=True, open_library_rate_limit=0.0,
    open_library_base_url="https://openlibrary.org")


def _politica(fuente: str) -> PoliticaFuente:
    return PoliticaFuente(fuente, fuente, 0.0, 1, 3)


@pytest.fixture
def ajustes_clientes(monkeypatch):
    monkeypatch.setattr("zascarr.config.get_settings", lambda: AJUSTES_CLIENTES)


def _transporte(handler):
    return httpx.MockTransport(handler)


async def test_gcd_get_series_por_id_lee_anios_y_404_es_none(ajustes_clientes):
    from zascarr.services.gcd import GCDClient

    def handler(request: httpx.Request) -> httpx.Response:
        if "series/77" in str(request.url):
            return httpx.Response(200, json={"name": "Batman", "year_began": 1940,
                                              "year_ended": 2011})
        return httpx.Response(404)

    async with GCDClient(politica=_politica("gcd"), transporte=_transporte(handler)) as c:
        ficha = await c.get_series_por_id(77)
        assert (ficha.year_began, ficha.year_ended) == (1940, 2011)
        assert await c.get_series_por_id(99) is None


async def test_gcd_un_429_es_transitorio_no_none(ajustes_clientes):
    from zascarr.services.gcd import GCDClient
    from zascarr.utils.peticiones import ErrorDePeticion

    async with GCDClient(politica=_politica("gcd"),
                         transporte=_transporte(lambda _r: httpx.Response(429, headers={
                             "retry-after": "0"}))) as c:
        with pytest.raises(ErrorDePeticion):
            await c.get_series_por_id(77)


async def test_metron_get_series_por_id_lee_descripcion_y_anios(ajustes_clientes):
    from zascarr.services.metron import MetronClient

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "id": 88, "series": "Batman", "year_began": 1940, "year_end": 2011,
            "desc": "Sinopsis", "resource_url": "https://metron.cloud/series/88/"})

    async with MetronClient(token="tok", politica=_politica("metron"),
                            transporte=_transporte(handler)) as c:
        ficha = await c.get_series_por_id(88)
    assert ficha.descripcion == "Sinopsis"
    assert (ficha.year_began, ficha.year_ended) == (1940, 2011)
    assert ficha.site_url == "https://metron.cloud/series/88/"


async def test_open_library_get_work_lee_descripcion_y_anio(ajustes_clientes):
    from zascarr.services.open_library import OpenLibraryClient

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "key": "/works/OL1W", "title": "Batman", "first_publish_year": 1939,
            "description": {"value": "Sinopsis de la obra"}})

    async with OpenLibraryClient(base_url="https://openlibrary.org",
                                 politica=_politica("open_library"),
                                 transporte=_transporte(handler)) as c:
        ficha = await c.get_work("OL1W")
    assert ficha.description == "Sinopsis de la obra" and ficha.start_year == 1939
    assert ficha.site_url == "https://openlibrary.org/works/OL1W"


async def test_open_library_sin_id_valido_no_pide(ajustes_clientes):
    from zascarr.services.open_library import OpenLibraryClient

    peticiones: list[str] = []

    async with OpenLibraryClient(base_url="https://openlibrary.org",
                                 politica=_politica("open_library"),
                                 transporte=_transporte(
                                     lambda r: peticiones.append(str(r.url))
                                     or httpx.Response(200, json={}))) as c:
        assert await c.get_work("no-es-una-obra") is None
    assert peticiones == []
