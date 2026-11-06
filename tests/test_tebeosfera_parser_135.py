"""Diagnóstico #135: el parser de Tebeosfera y una respuesta real de 2026-11-06.

El fixture es un fragmento recortado (contenedor + 3 primeras filas) de la respuesta real a
`busqueda="Dragon Ball"` en `T3_publicaciones`. Se guarda sin imágenes y sin el resto de filas
para no redistribuir contenido de terceros; el diagnóstico completo está en
`docs/design/diagnostico-tebeosfera-135-2026-11-06.md`.
"""
from __future__ import annotations

from pathlib import Path

from zascarr.services.tebeosfera import _parse_results

RAIZ = Path(__file__).resolve().parents[1]
FIXTURE = (RAIZ / "docs" / "design" / "fixtures-cobertura"
           / "tebeosfera_dragon_ball_2026-11-06.html")


def test_el_parser_lee_las_filas_reales_y_la_primera_no_es_la_busqueda():
    html = FIXTURE.read_text(encoding="utf-8")
    resultados = _parse_results(html, "collection")
    assert [r.title for r in resultados] == ["BATMAN", "BATMAN", "BOLA DE DRAC"]
    assert [r.slug for r in resultados] == [
        "batman_2009_planeta-deagostini_-barcelona-",
        "batman_2014_ecc_-en_barcelona-",
        "bola_de_drac_1992_planeta-deagostini_-col._superior-",
    ]
    # El contenedor real las agrupa todas: no hay un sidebar colándose por un XPath global.
    assert resultados[0].kind == "collection"
