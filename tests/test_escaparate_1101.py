"""#1101: modo Escaparate, precedencia y sugerencias."""
from __future__ import annotations

from pathlib import Path

from zascarr.web.library import _leer_filtros


def _leer(**kw):
    return _leer_filtros("1", kw.pop("q", ""), kw.pop("tradition", ""),
                         "", "", "", kw.pop("vista", ""), "", "", "", **kw)


def test_precedencia_escaparate():
    assert _leer().modo == "gestion"
    assert _leer(modo="escaparate").modo == "escaparate"
    assert _leer(modo="escaparate", q="thorgal").modo == "gestion"
    assert _leer(modo="escaparate", tradition="tebeo").modo == "gestion"
    assert _leer(modo="escaparate", vista="lista").modo == "gestion"
    assert _leer(modo="inventado").modo == "gestion"


def test_plantilla_escaparate_y_sugerencias():
    bib = Path("src/zascarr/web/templates/biblioteca.html").read_text()
    esc = Path("src/zascarr/web/templates/_escaparate.html").read_text()
    sug = Path("src/zascarr/web/templates/_sugerencias_escaparate.html").read_text()
    css = Path("src/zascarr/static/web.css").read_text()
    assert 'include "_escaparate.html"' in bib
    assert "Escaparate" in bib and "Gestión" in bib
    for bloque in ("Continuar leyendo", "Vistos recientemente", "Recién incorporados",
                   "Redescubre tu estantería", "Accesos rápidos", "Autores destacados"):
        assert bloque in esc
    assert "Cambiar sugerencias" in sug and "hx-get" in sug
    assert "sugerencias" in sug
    assert ".escaparate" in css and "@media (prefers-reduced-motion: reduce)" in css


def test_selector_aria_css_y_vacio():
    bib = Path("src/zascarr/web/templates/biblioteca.html").read_text()
    sug = Path("src/zascarr/web/templates/_sugerencias_escaparate.html").read_text()
    esc = Path("src/zascarr/web/templates/_escaparate.html").read_text()
    css = Path("src/zascarr/static/web.css").read_text()
    assert 'aria-current="page"' in bib and "selector-modo" in bib
    assert "No hay más sugerencias por ahora" in sug
    assert "min-width: 0" in css and "scrollbar-width: none" in css
    assert "::-webkit-scrollbar { display: none; }" in css
    assert "Todavía no hay actividad" in esc
    assert 'tabindex="0"' in esc and "ui.portada" in esc
    assert "ui.chip" in esc


def test_ficha_mas_de_la_serie_plantilla():
    ficha = Path("src/zascarr/web/templates/series_detail.html").read_text()
    assert "mas-serie" in ficha and "mas_serie" in ficha and "escaparate-tarjeta" in ficha
