"""#1044: visor de portada HD (plantilla/JS estático y orden canónico)."""
from __future__ import annotations

from pathlib import Path

from zascarr.services import portada_numero


def test_constantes_hd_y_plantilla_dialogo():
    assert portada_numero.ANCHO_HD == 1200
    assert portada_numero.MAX_PIXELES_HD >= 12_000_000
    ficha = Path("src/zascarr/web/templates/series_detail.html").read_text()
    visor = Path("src/zascarr/web/templates/_visor_portada.html").read_text()
    rejilla = Path("src/zascarr/web/templates/_rejilla_biblioteca.html").read_text()
    base = Path("src/zascarr/web/templates/base.html").read_text()
    js = Path("src/zascarr/static/visor-portada.js").read_text()
    assert '_visor_portada.html' in ficha
    assert '<dialog id="visor-portada"' in visor
    assert "data-visor-src" in ficha and "data-visor-prev" in ficha and "data-visor-next" in ficha
    assert "portada-hd.jpg" in ficha
    assert "visor-portada-boton" in ficha and 'href="/ui/series/' in ficha
    assert "visor-portada-boton" in rejilla and "portada-hd.jpg" in rejilla
    assert "visor-portada.js" in base
    assert "restaurar" not in js and "invocador.focus()" in js and "showModal" in js
    assert "ArrowLeft" in js and "ArrowRight" in js


def test_biblioteca_incluye_el_dialogo_en_el_cuerpo():
    bib = Path("src/zascarr/web/templates/biblioteca.html").read_text()
    head, body = bib.split("{% block content %}", 1)
    assert '_visor_portada.html' in body
    assert '_visor_portada.html' not in head
