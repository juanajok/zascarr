"""QA #526: en el filtro de año de GCD, solo el 404 cae al path normal."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from zascarr.services import gcd as modulo
from zascarr.services.gcd import GCDClient
from zascarr.utils.peticiones import (
    ErrorDePeticion,
    ReintentosAgotados,
    RespuestaNoTransitoria,
)


def _item():
    return {"api_url": "https://www.comics.org/api/series/1/",
            "name": "Dragon Ball", "language": "es", "country": "es"}


class TestSolo404CaeAlNormal:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc", [
        ReintentosAgotados("gcd", 3, 429),
        ReintentosAgotados("gcd", 2, 503),
        RespuestaNoTransitoria(403),
        ErrorDePeticion("transporte"),
    ])
    async def test_errores_del_anio_se_propagan_y_no_cachean(self, monkeypatch, exc):
        async def falla(*_a, **_k):
            raise exc
        monkeypatch.setattr(modulo, "pedir_con_cortesia", falla)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        with pytest.raises(type(exc)):
            await cliente.search_series("Dragon Ball", anio=2006)
        assert modulo._CACHE_BUSQUEDAS == {}

    @pytest.mark.asyncio
    async def test_json_roto_del_anio_se_propaga(self, monkeypatch):
        async def roto(*_a, **_k):
            return httpx.Response(200, text="no es json")
        monkeypatch.setattr(modulo, "pedir_con_cortesia", roto)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        with pytest.raises(Exception) as exc:
            await cliente.search_series("Dragon Ball", anio=2006)
        assert not isinstance(exc.value, AssertionError)
        assert modulo._CACHE_BUSQUEDAS == {}

    @pytest.mark.asyncio
    async def test_404_del_anio_si_cae_al_path_normal(self, monkeypatch):
        llamadas = []

        async def pedir(_c, _m, url, **_k):
            llamadas.append(url)
            if "/year/" in url:
                raise RespuestaNoTransitoria(404)
            return httpx.Response(200, json={"results": [_item()], "next": None})
        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        resultados = await cliente.search_series("Dragon Ball", anio=2006)
        assert [r.name for r in resultados] == ["Dragon Ball"]
        assert len(llamadas) == 2 and "?page=1" in llamadas[1]


class TestUltimasPeticiones:
    @pytest.mark.asyncio
    async def test_consulta_vacia_resetea_el_contador(self):
        cliente = GCDClient()
        cliente.ultimas_peticiones = 99
        assert await cliente.search_series("   ") == []
        assert cliente.ultimas_peticiones == 0

    @pytest.mark.asyncio
    async def test_la_cache_tambien_resetea_a_cero(self, monkeypatch):
        async def pedir(*_a, **_k):
            return httpx.Response(200, json={"results": [_item()], "next": None})
        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        await cliente.search_series("Dragon Ball")
        cliente.ultimas_peticiones = 99
        await cliente.search_series("Dragon Ball")
        assert cliente.ultimas_peticiones == 0
