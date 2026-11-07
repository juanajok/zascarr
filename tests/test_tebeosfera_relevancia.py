"""BL-FU3 (#466): Tebeosfera ordena los candidatos por relevancia sin descartar.

Sin red: el orden es una función pura y `search_series` se prueba con `_search_table`
parcheado. El fixture es el HTML real recortado del diagnóstico de #135.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from zascarr.services.tebeosfera import (
    TebeosferaClient,
    TebeosferaResult,
    _parse_results,
    ordenar_por_relevancia,
)

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = (RAIZ / "docs" / "design" / "fixtures-cobertura"
           / "tebeosfera_dragon_ball_2026-11-06.html")


def _fila(slug: str, titulo: str, kind: str = "collection") -> TebeosferaResult:
    return TebeosferaResult(slug=slug, title=titulo, kind=kind)


class TestOrdenPorRelevancia:
    def test_dragon_ball_el_acierto_va_antes_que_batman(self):
        resultados = _parse_results(FIXTURE.read_text(encoding="utf-8"), "collection")
        assert [r.title for r in resultados] == ["BATMAN", "BATMAN", "BOLA DE DRAC"]
        ordenados = ordenar_por_relevancia(resultados, "Dragon Ball")
        assert [r.title for r in ordenados][:1] == ["BOLA DE DRAC"]
        assert len(ordenados) == len(resultados)          # no se descarta nada
        assert {r.slug for r in ordenados} == {r.slug for r in resultados}

    def test_mortadelo_relacionado_antes_sin_descartar_ajenos(self):
        resultados = [
            _fila("alegres", "ALEGRES HISTORIETAS"),
            _fila("historia", "HISTORIA DEL DINERO"),
            _fila("mortadelo", "MORTADELO Y FILEMÓN -LA GRAN AVENTURA-", "saga"),
        ]
        ordenados = ordenar_por_relevancia(resultados, "Mortadelo y Filemón")
        assert ordenados[0].title == "MORTADELO Y FILEMÓN -LA GRAN AVENTURA-"
        assert [r.title for r in ordenados] == [
            "MORTADELO Y FILEMÓN -LA GRAN AVENTURA-",
            "HISTORIA DEL DINERO",
            "ALEGRES HISTORIETAS",
        ]
        assert "ALEGRES HISTORIETAS" in {r.title for r in ordenados}  # no se descarta

    def test_sin_coincidencia_conserva_el_orden_original(self):
        resultados = [
            _fila("a", "BATMAN"), _fila("b", "THORGAL"), _fila("c", "MORTADELO"),
        ]
        ordenados = ordenar_por_relevancia(resultados, "consulta sin relación")
        assert [r.slug for r in ordenados] == ["a", "b", "c"]

    def test_normaliza_mayusculas_y_acentos(self):
        resultados = [_fila("x", "BATMAN"), _fila("y", "DRAGÓN BALL")]
        ordenados = ordenar_por_relevancia(resultados, "dragon ball")
        assert ordenados[0].title == "DRAGÓN BALL"

    def test_es_estable_y_no_muta_la_lista_original(self):
        resultados = [_fila("a", "BATMAN"), _fila("b", "BATMAN")]
        ordenados = ordenar_por_relevancia(resultados, "dragon ball")
        assert [r.slug for r in ordenados] == ["a", "b"]
        assert [r.slug for r in resultados] == ["a", "b"]


class TestSearchSeriesAplicaElOrden:
    @pytest.mark.asyncio
    async def test_ordena_antes_de_recortar_a_limit(self):
        cliente = TebeosferaClient()
        batman = _fila("batman", "BATMAN", "collection")
        bola = _fila("bola", "BOLA DE DRAC", "collection")
        cliente._search_table = AsyncMock(side_effect=lambda tabla, _kind, _q: (
            [batman, batman, bola] if tabla == "T3_publicaciones" else []))
        resultados = await cliente.search_series("Dragon Ball", limit=2)
        assert [r.title for r in resultados] == ["BOLA DE DRAC", "BATMAN"]
        assert cliente._search_table.await_count == 2
