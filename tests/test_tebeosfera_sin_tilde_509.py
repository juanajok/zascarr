"""BL-FU8 (#509): último escalón sin diacríticos. Sin red."""
from __future__ import annotations

import httpx
import pytest

from zascarr.services import tebeosfera as modulo
from zascarr.services.tebeosfera import (
    TebeosferaClient,
    _parse_results,
    _sin_diacriticos,
)

HTML_RESULTADO = (
    '<div class="linea_resultados"><a href="/colecciones/tintin_1990.html">'
    'TINTIN (1990)</a></div>'
)
LARGA = "Tintín El país del oro negro"


def _resultado():
    return _parse_results(HTML_RESULTADO, "collection")[0]


def test_quita_solo_diacriticos():
    assert _sin_diacriticos("Tintín") == "Tintin"
    assert _sin_diacriticos("Astérix") == "Asterix"
    assert _sin_diacriticos("Tintin") == "Tintin"


class TestEscalonSinTilde:
    @pytest.mark.asyncio
    async def test_primera_palabra_acentuada_vacia_prueba_sin_tilde(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            if query == "Tintin":
                return [_resultado()] if tabla == "T3_publicaciones" else []
            return []

        cliente._search_table = tabla
        resultados = await cliente.search_series(LARGA)
        assert [r.slug for r in resultados] == ["tintin_1990"]
        assert len(llamadas) == 8
        assert [q for _, _, q in llamadas] == [
            LARGA, LARGA, "Tintín país oro", "Tintín país oro",
            "Tintín", "Tintín", "Tintin", "Tintin",
        ]

    @pytest.mark.asyncio
    async def test_si_la_acentuada_devuelve_no_prueba_sin_tilde(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            if query == "Tintín" and tabla == "T3_publicaciones":
                return [_resultado()]
            return []

        cliente._search_table = tabla
        resultados = await cliente.search_series(LARGA)
        assert resultados
        assert len(llamadas) == 6   # normal + 3 palabras + Tintín; para ahí
        assert "Tintin" not in [q for _, _, q in llamadas]

    @pytest.mark.asyncio
    async def test_palabra_sin_acento_no_tiene_escalon(self):
        cliente = TebeosferaClient()
        llamadas = []

        async def tabla(tabla, kind, query):
            llamadas.append((tabla, kind, query))
            return []

        cliente._search_table = tabla
        assert await cliente.search_series("Tintin") == []
        assert len(llamadas) == 2

    @pytest.mark.asyncio
    async def test_fallback_completo_cuesta_8_post_y_por_cortesia(self, monkeypatch):
        cliente = TebeosferaClient()
        respuestas = [httpx.Response(200, text="") for _ in range(6)]
        respuestas += [httpx.Response(200, text=HTML_RESULTADO),
                       httpx.Response(200, text="")]
        llamadas = []

        async def pedir(_cliente, metodo, url, **kwargs):
            llamadas.append((metodo, kwargs.get("datos")))
            return respuestas.pop(0)

        monkeypatch.setattr(modulo, "pedir_con_cortesia", pedir)
        async with cliente:
            resultados = await cliente.search_series(LARGA)
        assert resultados and resultados[0].slug == "tintin_1990"
        assert len(llamadas) == 8
        assert all(metodo == "POST" for metodo, _ in llamadas)
        assert [datos["busqueda"] for _, datos in llamadas] == [
            LARGA, LARGA, "Tintín país oro", "Tintín país oro",
            "Tintín", "Tintín", "Tintin", "Tintin",
        ]
