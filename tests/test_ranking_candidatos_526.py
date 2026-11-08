"""BL-FU13 (#526): ranking explicable y filtro de año en GCD. Sin red."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from zascarr.models import MetadataSource
from zascarr.services import gcd as modulo_gcd
from zascarr.services.descubrimiento_grupo import ordenar_candidatos
from zascarr.services.discovery import Busqueda, DiscoveryResult
from zascarr.services.gcd import GCDClient
from zascarr.utils.peticiones import RespuestaNoTransitoria


def _cand(nombre, anio, editorial="Planeta DeAgostini", pais="es", idioma="es"):
    return SimpleNamespace(name=nombre, start_year=anio, publisher=editorial,
                           country=pais, language=idioma)


class TestRanking:
    def test_anio_2006_gana_frente_a_1992_y_al_reves(self):
        candidatos = [_cand("Dragon Ball", 1992), _cand("Dragon Ball Ultimate", 2006)]
        assert ordenar_candidatos(
            candidatos, "Dragon Ball", anio_esperado=2006)[0].start_year == 2006
        assert ordenar_candidatos(
            candidatos, "Dragon Ball", anio_esperado=1992)[0].start_year == 1992

    def test_editorial_esperada_desempata(self):
        candidatos = [
            _cand("Dragon Ball", 2006, editorial="Otra Editorial"),
            _cand("Dragon Ball", 2006, editorial="Planeta DeAgostini"),
        ]
        elegido = ordenar_candidatos(
            candidatos, "Dragon Ball", anio_esperado=2006,
            editorial_esperada="Planeta DeAgostini")[0]
        assert elegido.publisher == "Planeta DeAgostini"

    def test_sin_expectativas_estable_y_no_descarta(self):
        candidatos = [_cand("B", 2000), _cand("A", 1990), _cand("C", 2010)]
        orden = ordenar_candidatos(candidatos, "Dragon Ball")
        assert len(orden) == 3
        assert [c.name for c in orden] == [
            c.name for c in ordenar_candidatos(candidatos, "Dragon Ball")]

    def test_los_campos_ausentes_no_suman(self):
        sin_datos = SimpleNamespace(name="Dragon Ball")
        con_datos = _cand("Dragon Ball", 2006)
        orden = ordenar_candidatos(
            [sin_datos, con_datos], "Dragon Ball", anio_esperado=2006)
        assert orden[0] is con_datos

    def test_descubrimiento_grupo_ordena_sin_expectativas(self):
        from zascarr.services.descubrimiento_grupo import DescubrimientoDeGrupo

        resultados = [
            DiscoveryResult(source=MetadataSource.GCD, external_id="1", title="Zeta",
                            start_year=2000, description=None, cover_url=None,
                            site_url=None),
            DiscoveryResult(source=MetadataSource.GCD, external_id="2", title="Alfa",
                            start_year=2000, description=None, cover_url=None,
                            site_url=None),
        ]
        busqueda = Busqueda(resultados, [], {})
        orden = DescubrimientoDeGrupo._ordenar(busqueda, "consulta")
        assert len(orden) == 2
        assert [r.title for r in orden] == [
            r.title for r in DescubrimientoDeGrupo._ordenar(busqueda, "consulta")]


class TestGCDConAnio:
    @pytest.mark.asyncio
    async def test_usa_el_path_de_anio_en_una_peticion(self, monkeypatch):
        respuesta = httpx.Response(200, json={"results": [{
            "api_url": "https://www.comics.org/api/series/99/",
            "name": "Dragon Ball Ultimate", "year_began": 2006,
            "language": "es", "country": "es"}]})
        llamadas = []

        async def pedir(_cliente, _metodo, url, **_kwargs):
            llamadas.append(url)
            return respuesta

        monkeypatch.setattr(modulo_gcd, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        resultados = await cliente.search_series("Dragon Ball", limit=10, anio=2006)
        assert [r.name for r in resultados] == ["Dragon Ball Ultimate"]
        assert len(llamadas) == 1
        assert llamadas[0].endswith("/series/name/Dragon%20Ball/year/2006/")

    @pytest.mark.asyncio
    async def test_si_el_anio_falla_cae_al_path_normal(self, monkeypatch):
        normal = httpx.Response(200, json={
            "next": None,
            "results": [{"api_url": "https://www.comics.org/api/series/1/",
                         "name": "Dragon Ball 1992", "year_began": 1992,
                         "language": "es", "country": "es"}]})
        llamadas = []

        async def pedir(_cliente, _metodo, url, **_kwargs):
            llamadas.append(url)
            if "/year/" in url:
                raise RespuestaNoTransitoria(404)
            return normal

        monkeypatch.setattr(modulo_gcd, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        resultados = await cliente.search_series("Dragon Ball", limit=10, anio=2006)
        assert [r.name for r in resultados] == ["Dragon Ball 1992"]
        assert len(llamadas) == 2
        assert llamadas[0].endswith("/year/2006/")
        assert "?page=1" in llamadas[1]
