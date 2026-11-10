"""BL-INF4: la previa solo se muestra en el número que se está mirando (regresión)."""
from __future__ import annotations

from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "src/zascarr/static/web.css").read_text()


def test_la_previa_se_muestra_solo_con_hover_o_foco_del_chip():
    assert ".chip-previa:hover > .previa-numero:not(:empty)" in CSS
    assert ".chip-previa:focus-within > .previa-numero:not(:empty)" in CSS
    # Por defecto, oculta: si no, se acumularían las de los chips ya visitados.
    assert "  display: none; overflow: hidden;" in CSS


def test_sigue_oculta_en_movil_y_puntero_grueso():
    regla = "@media (max-width: 860px), (pointer: coarse) { .previa-numero { display: none; } }"
    assert regla in CSS
