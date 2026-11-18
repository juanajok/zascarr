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
    assert "Cambiar sugerencias" in esc and "hx-get" in esc
    assert "sugerencias" in sug
    assert ".escaparate" in css and "@media (prefers-reduced-motion: reduce)" in css
