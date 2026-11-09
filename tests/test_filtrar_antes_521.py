"""BL-FU11 (#521): filtrar por país/idioma antes de recortar. Sin red."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from zascarr.services import gcd as modulo_gcd
from zascarr.services.comic_vine import ComicVineClient
from zascarr.services.gcd import GCDClient


def _item(gcd_id: int, nombre: str, *, language: str | None, country: str | None):
    return {
        "api_url": f"https://www.comics.org/api/series/{gcd_id}/",
        "name": nombre,
        "year_began": 1990,
        "language": language,
        "country": country,
    }


def _json(items):
    return {"results": items}


class TestGCDAntesDeRecortar:
    @pytest.mark.asyncio
    async def test_espanoles_despues_de_diez_extranjeros(self, monkeypatch):
        extranjeros = [_item(i, f"Foreign {i}", language="en", country="us")
                       for i in range(1, 11)]
        espanoles = [_item(11, "Thorgal ES", language="es", country="es"),
                     _item(12, "Mortadelo ES", language="es", country="es")]
        respuesta = httpx.Response(200, json=_json(extranjeros + espanoles))
        monkeypatch.setattr(modulo_gcd, "pedir_con_cortesia",
                            AsyncMock(return_value=respuesta))
        cliente = GCDClient()
        cliente._client = AsyncMock()
        resultados = await cliente.search_series("thorgal", limit=2)
        assert [r.name for r in resultados] == ["Thorgal ES", "Mortadelo ES"]
        assert len(resultados) == 2

    @pytest.mark.asyncio
    async def test_todos_extranjeros_devuelve_vacio(self, monkeypatch):
        respuesta = httpx.Response(200, json=_json(
            [_item(i, f"Foreign {i}", language="en", country="us") for i in range(12)]))
        monkeypatch.setattr(modulo_gcd, "pedir_con_cortesia",
                            AsyncMock(return_value=respuesta))
        cliente = GCDClient()
        cliente._client = AsyncMock()
        assert await cliente.search_series("x", limit=10) == []

    @pytest.mark.asyncio
    async def test_mixtos_respetan_limit_y_conservan_sin_dato(self, monkeypatch):
        items = [
            _item(1, "Foreign", language="en", country="us"),
            _item(2, "Sin dato", language=None, country=None),
            _item(3, "ES 1", language="es", country="es"),
            _item(4, "ES 2", language="es", country="es"),
        ]
        respuesta = httpx.Response(200, json=_json(items))
        monkeypatch.setattr(modulo_gcd, "pedir_con_cortesia",
                            AsyncMock(return_value=respuesta))
        cliente = GCDClient()
        cliente._client = AsyncMock()
        resultados = await cliente.search_series("x", limit=2)
        assert [r.name for r in resultados] == ["Sin dato", "ES 1"]


class TestComicVinePideLimitYRecorta:
    @pytest.mark.asyncio
    async def test_pide_50_y_entrega_limit(self):
        cliente = ComicVineClient()
        resultados_api = [
            {"id": i, "name": f"Serie {i}", "start_year": 2000,
             "image": {"medium_url": None}} for i in range(60)
        ]
        cliente._get = AsyncMock(return_value={"results": resultados_api})
        resultados = await cliente.search_series("x", limit=3)
        assert len(resultados) == 3
        assert [r.cv_id for r in resultados] == [0, 1, 2]
        params = cliente._get.await_args.args[1]
        assert params["limit"] == 3
        assert params["resources"] == "volume"
