"""BL-FU6 (#500): fallback de consulta corta en Tebeosfera. Sin red."""
from __future__ import annotations

import httpx
import pytest

from zascarr.services import tebeosfera as modulo
from zascarr.services.tebeosfera import (
    TebeosferaClient,
    _consulta_simplificada,
    _parse_results,
)

HTML_RESULTADO = (
    '<div class="linea_resultados"><a href="/colecciones/tintin_1990_juventud.html">'
    'TINTÍN (1990, JUVENTUD)</a></div>'
)


class TestSimplificacion:
    @pytest.mark.parametrize("larga,corta", [
        ("Tintín: El país del oro negro", "Tintín"),
        ("Astérix y los godos", "Astérix godos"),
        ("Mortadelo y Filemón -La gran aventura-", "Mortadelo Filemón gran"),
    ])
    def test_ejemplos(self, larga, corta):
        assert _consulta_simplificada(larga) == corta

    def test_una_palabra_o_sin_cambio_no_reintenta(self):
        assert _consulta_simplificada("Tintín") is None
        assert _consulta_simplificada("Todo Mafalda") is None
        assert _consulta_simplificada("") is None


class TestSearchSeriesFallback:
    @pytest.mark.asyncio
    async def test_si_la_larga_no_da_nada_reintenta_una_vez(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            if query == "Tintín: El país del oro negro":
                return []
            if tabla != "T3_publicaciones":
                return []
            return [_parse_results(HTML_RESULTADO, "collection")[0]]

        cliente._search_table = tabla
        resultados = await cliente.search_series("Tintín: El país del oro negro")
        assert [r.slug for r in resultados] == ["tintin_1990_juventud"]
        assert llamadas == [
            ("T3_publicaciones", "collection", "Tintín: El país del oro negro"),
            ("T3_series", "saga", "Tintín: El país del oro negro"),
            ("T3_publicaciones", "collection", "Tintín"),
            ("T3_series", "saga", "Tintín"),
        ]

    @pytest.mark.asyncio
    async def test_si_la_larga_da_algo_no_hay_reintento(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            return [_parse_results(HTML_RESULTADO, "collection")[0]]

        cliente._search_table = tabla
        await cliente.search_series("Tintín")
        assert len(llamadas) == 2 and all(q == "Tintín" for _, _, q in llamadas)

    @pytest.mark.asyncio
    async def test_consulta_de_una_palabra_vacia_no_reintenta(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            return []

        cliente._search_table = tabla
        assert await cliente.search_series("Tintín") == []
        assert len(llamadas) == 2

    @pytest.mark.asyncio
    async def test_el_fallback_pasa_por_la_cortesia(self, monkeypatch):
        cliente = TebeosferaClient()
        respuestas = [
            httpx.Response(200, text=""),
            httpx.Response(200, text=""),
            httpx.Response(200, text=HTML_RESULTADO),
            httpx.Response(200, text=""),
        ]
        llamadas = []

        async def pedir(_cliente, metodo, url, **kwargs):
            llamadas.append((metodo, kwargs.get("datos")))
            return respuestas.pop(0)

        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        async with cliente:
            resultados = await cliente.search_series("Tintín: El país del oro negro")
        assert resultados and resultados[0].slug == "tintin_1990_juventud"
        assert len(llamadas) == 4
        assert all(metodo == "POST" for metodo, _ in llamadas)
        assert [datos["busqueda"] for _, datos in llamadas] == [
            "Tintín: El país del oro negro", "Tintín: El país del oro negro",
            "Tintín", "Tintín"]
