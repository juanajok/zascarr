"""BL-INF10: progreso en la tarjeta y color de las pastillas de número."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
REJILLA = (RAIZ / "src/zascarr/web/templates/_rejilla_biblioteca.html").read_text()
FICHA = (RAIZ / "src/zascarr/web/templates/series_detail.html").read_text()
CSS = (RAIZ / "src/zascarr/static/web.css").read_text()

def test_la_tarjeta_pinta_una_barra_accesible_bajo_la_portada():
    assert "library-card-progreso" in REJILLA and "barra-lectura" in REJILLA
    assert 'role="progressbar"' in REJILLA
    assert "aria-valuenow=" in REJILLA and "% leído" in REJILLA

def test_las_pastillas_distinguen_leido_y_leyendo():
    assert "issue-leido" in FICHA and "issue-leyendo" in FICHA
    assert 'lectura.estado == "completed"' in FICHA
    assert 'lectura.estado == "reading"' in FICHA
    assert "leído" in FICHA and "leyendo" in FICHA   # texto sr, no solo color

def test_los_colores_usan_los_tokens_de_la_app():
    assert ".issue-chip.issue-present.issue-leido" in CSS
    assert "background: var(--ink); color: var(--paper)" in CSS
    assert ".issue-chip.issue-present.issue-leyendo" in CSS
    assert "background: var(--amber-bg); color: var(--ink)" in CSS
    assert ".barra-lectura-relleno" in CSS and "background: var(--ok-solid)" in CSS
