"""BL-FU12 (#523): GCD pagina con filtro español y caché. Sin red."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from zascarr.services import gcd as modulo
from zascarr.services.gcd import GCDClient, limpiar_cache_busquedas


def _item(gcd_id: int, *, language="es", country="es", name=None):
    return {
        "api_url": f"https://www.comics.org/api/series/{gcd_id}/",
        "name": name or f"Serie {gcd_id}",
        "language": language,
        "country": country,
    }


def _pagina(items, *, next_url=None):
    return {"results": items, "next": next_url}


class _Respuestas:
    def __init__(self, paginas):
        self.paginas = list(paginas)
        self.urls = []

    async def __call__(self, _cliente, _metodo, url, **_kwargs):
        self.urls.append(url)
        return httpx.Response(200, json=self.paginas.pop(0))


class TestPaginacion:
    @pytest.mark.asyncio
    async def test_pagina_1_sin_espanoles_pagina_2_con_ellos(self):
        respuestas = _Respuestas([
            _pagina([_item(i, language="en", country="us") for i in range(1, 11)],
                    next_url="?page=2"),
            _pagina([_item(11, name="Dragon Ball Ultimate")], next_url=None),
        ])
        cliente = GCDClient()
        cliente._client = AsyncMock()
        original = modulo.pedir_con_cortesia
        modulo.pedir_con_cortesia = respuestas
        try:
            resultados = await cliente.search_series("Dragon Ball", limit=10)
        finally:
            modulo.pedir_con_cortesia = original
        assert [r.name for r in resultados] == ["Dragon Ball Ultimate"]
        assert len(respuestas.urls) == 2
        assert respuestas.urls[0].endswith("/?page=1")
        assert respuestas.urls[1].endswith("/?page=2")

    @pytest.mark.asyncio
    async def test_pagina_1_suficiente_solo_una_peticion(self):
        respuestas = _Respuestas([
            _pagina([_item(1, name="ES 1")], next_url="?page=2"),
        ])
        cliente = GCDClient()
        cliente._client = AsyncMock()
        original = modulo.pedir_con_cortesia
        modulo.pedir_con_cortesia = respuestas
        try:
            resultados = await cliente.search_series("x", limit=1)
        finally:
            modulo.pedir_con_cortesia = original
        assert [r.name for r in resultados] == ["ES 1"]
        assert len(respuestas.urls) == 1

    @pytest.mark.asyncio
    async def test_tope_duro_de_tres_paginas(self):
        paginas = [
            _pagina([_item(i, language="en", country="us") for i in range(1, 11)],
                    next_url="?page=2") for _ in range(3)
        ]
        respuestas = _Respuestas(paginas)
        cliente = GCDClient()
        cliente._client = AsyncMock()
        original = modulo.pedir_con_cortesia
        modulo.pedir_con_cortesia = respuestas
        try:
            resultados = await cliente.search_series("x", limit=10)
        finally:
            modulo.pedir_con_cortesia = original
        assert resultados == []
        assert len(respuestas.urls) == 3

    @pytest.mark.asyncio
    async def test_segunda_busqueda_igual_usa_cache_sin_peticiones(self):
        respuestas = _Respuestas([
            _pagina([_item(1, name="ES 1")], next_url=None),
        ])
        cliente = GCDClient()
        cliente._client = AsyncMock()
        original = modulo.pedir_con_cortesia
        modulo.pedir_con_cortesia = respuestas
        try:
            primera = await cliente.search_series("Dragon Ball", limit=10)
            segunda = await cliente.search_series("  dragon   ball ", limit=10)
        finally:
            modulo.pedir_con_cortesia = original
        assert primera == segunda
        assert len(respuestas.urls) == 1

    def test_limpiar_cache(self):
        limpiar_cache_busquedas()
        assert modulo._CACHE_BUSQUEDAS == {}
