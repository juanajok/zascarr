"""QA #526: caché/errores/paginación de GCD no ocultan fallos técnicos."""
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


def _item(gcd_id=1, name="Dragon Ball"):
    return {"api_url": f"https://www.comics.org/api/series/{gcd_id}/",
            "name": name, "language": "es", "country": "es"}


class TestErroresNoSeCachean:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc", [
        ReintentosAgotados("gcd", 3, 429),
        ReintentosAgotados("gcd", 2, 503),
        RespuestaNoTransitoria(403),
        ErrorDePeticion("red"),
    ])
    async def test_un_fallo_propaga_y_no_deja_cache_vacia(self, monkeypatch, exc):
        async def falla(*_a, **_k):
            raise exc
        monkeypatch.setattr(modulo, "pedir_con_cortesia", falla)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        with pytest.raises(type(exc)):
            await cliente.search_series("Dragon Ball")
        assert modulo._CACHE_BUSQUEDAS == {}

    @pytest.mark.asyncio
    async def test_json_invalido_propaga_y_no_cachea(self, monkeypatch):
        async def roto(*_a, **_k):
            return httpx.Response(200, text="no es json")
        monkeypatch.setattr(modulo, "pedir_con_cortesia", roto)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        with pytest.raises(ErrorDePeticion):
            await cliente.search_series("Dragon Ball")
        assert modulo._CACHE_BUSQUEDAS == {}


class TestCachePorLimitYAcotada:
    @pytest.mark.asyncio
    async def test_el_limit_forma_parte_de_la_clave(self, monkeypatch):
        llamadas = []

        async def pedir(*_a, **_k):
            llamadas.append(1)
            return httpx.Response(200, json={"results": [_item()], "next": None})
        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        await cliente.search_series("Dragon Ball", limit=1)
        await cliente.search_series("Dragon Ball", limit=10)
        assert len(llamadas) == 2

    @pytest.mark.asyncio
    async def test_la_cache_no_crece_sin_limite(self, monkeypatch):
        async def pedir(*_a, **_k):
            return httpx.Response(200, json={"results": [_item()], "next": None})
        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        for i in range(130):
            await cliente.search_series(f"consulta {i}", limit=10)
        assert len(modulo._CACHE_BUSQUEDAS) <= 128


class TestAnioVacio:
    @pytest.mark.asyncio
    async def test_200_con_results_vacio_cae_al_path_normal(self, monkeypatch):
        llamadas = []

        async def pedir(_c, _m, url, **_k):
            llamadas.append(url)
            if "/year/" in url:
                return httpx.Response(200, json={"results": []})
            return httpx.Response(200, json={"results": [_item()], "next": None})
        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        resultados = await cliente.search_series("Dragon Ball", anio=2006)
        assert [r.name for r in resultados] == ["Dragon Ball"]
        assert len(llamadas) == 2
        assert "/year/2006/" in llamadas[0] and "?page=1" in llamadas[1]
