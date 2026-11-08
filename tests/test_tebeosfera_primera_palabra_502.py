"""BL-FU7 (#502): segundo escalón del fallback, primera palabra. Sin red."""
from __future__ import annotations

import httpx
import pytest

from zascarr.services import tebeosfera as modulo
from zascarr.services.tebeosfera import TebeosferaClient, _parse_results

HTML_RESULTADO = (
    '<div class="linea_resultados"><a href="/colecciones/asterix_1990.html">'
    'ASTÉRIX (1990)</a></div>'
)


def _resultado():
    return _parse_results(HTML_RESULTADO, "collection")[0]


class TestSegundoEscalon:
    @pytest.mark.asyncio
    async def test_tres_palabras_vacia_prueba_la_primera(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            if query == "Astérix":
                return [_resultado()] if tabla == "T3_publicaciones" else []
            return []

        cliente._search_table = tabla
        resultados = await cliente.search_series("Astérix y los godos")
        assert [r.slug for r in resultados] == ["asterix_1990"]
        assert llamadas == [
            ("T3_publicaciones", "collection", "Astérix y los godos"),
            ("T3_series", "saga", "Astérix y los godos"),
            ("T3_publicaciones", "collection", "Astérix godos"),
            ("T3_series", "saga", "Astérix godos"),
            ("T3_publicaciones", "collection", "Astérix"),
            ("T3_series", "saga", "Astérix"),
        ]

    @pytest.mark.asyncio
    async def test_si_tres_palabras_da_no_hay_segundo_reintento(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            if query == "Astérix godos" and tabla == "T3_publicaciones":
                return [_resultado()]
            return []

        cliente._search_table = tabla
        resultados = await cliente.search_series("Astérix y los godos")
        assert resultados
        assert len(llamadas) == 4
        assert all(query != "Astérix" for _, _, query in llamadas)

    @pytest.mark.asyncio
    async def test_consulta_de_una_palabra_no_tiene_escalones(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            return []

        cliente._search_table = tabla
        assert await cliente.search_series("Astérix") == []
        assert len(llamadas) == 2

    @pytest.mark.asyncio
    async def test_fallback_completo_pasa_por_cortesia_y_cuesta_6_post(
            self, monkeypatch):
        cliente = TebeosferaClient()
        respuestas = [
            httpx.Response(200, text=""),
            httpx.Response(200, text=""),
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
            resultados = await cliente.search_series("Astérix y los godos")
        assert resultados and resultados[0].slug == "asterix_1990"
        assert len(llamadas) == 6
        assert all(metodo == "POST" for metodo, _ in llamadas)
        assert [datos["busqueda"] for _, datos in llamadas] == [
            "Astérix y los godos", "Astérix y los godos",
            "Astérix godos", "Astérix godos",
            "Astérix", "Astérix",
        ]
