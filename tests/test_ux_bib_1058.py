"""#1058: densidad, modo, chips y atajo de búsqueda."""
from __future__ import annotations

from pathlib import Path

from zascarr.web.library import Filtros, _leer_filtros, _qs


def _leer(**kw):
    return _leer_filtros("1", "", "", "", "", "", "", "", "", "", **kw)


def test_densidad_valida_y_canonica():
    assert _leer().densidad == "intermedia"
    assert _leer(densidad="grande").densidad == "grande"
    assert _leer(densidad="compacta").densidad == "compacta"
    assert _leer(densidad="inventada").densidad == "intermedia"
    f = Filtros(densidad="grande", q="bat")
    assert "densidad=grande" in _qs(f, page=1)
    assert "densidad" not in _qs(Filtros(densidad="intermedia"), page=1)
    assert "q=bat" in _qs(f, page=1)


def test_modo_precedencia_y_aviso():
    assert _leer().modo == "gestion"
    esc = _leer(modo="escaparate")
    assert esc.modo == "gestion"
    assert any("escaparate" in aviso for aviso in esc.avisos)
    assert _leer(modo="otro").modo == "gestion"


def test_url_chip_conserva_filtros():
    from zascarr.web.library import url_chip
    f = Filtros(q="thorgal", orden="reciente")
    url = url_chip(f, "tradition", "europeo")
    assert "q=thorgal" in url and "tradition=europeo" in url and "orden=reciente" in url


def test_plantilla_control_densidad_y_chips():
    control = Path("src/zascarr/web/templates/_control_vista.html").read_text()
    rejilla = Path("src/zascarr/web/templates/_rejilla_biblioteca.html").read_text()
    assert "control-densidad" in control and "Grande" in control and "Compacta" in control
    assert "library-grid-{{ densidad }}" in rejilla
    assert "url_chip" in rejilla and "chip-filtro" in rejilla
    assert "<a class=\"library-card\"" in rejilla


def test_atajo_solo_biblioteca():
    base = Path("src/zascarr/web/templates/base.html").read_text()
    bib = Path("src/zascarr/web/templates/biblioteca.html").read_text()
    js = Path("src/zascarr/static/biblioteca-atajo.js").read_text()
    assert "biblioteca-atajo.js" in bib and "biblioteca-atajo.js" not in base
    assert "isContentEditable" in js and "input, textarea, select" in js
    assert "ctrlKey" in js and "f-q" in js
