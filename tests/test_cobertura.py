"""#449 BL-INF3: textos y CSS del bloque de cobertura."""
from pathlib import Path


def test_css_de_cobertura_usa_cifras_tabulares_y_rejilla_estrecha():
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".cobertura-numero" in css and "font-variant-numeric: tabular-nums" in css
    assert "minmax(220px, 1fr)" in css
    assert "@media (max-width: 480px)" in css
