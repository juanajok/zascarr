"""#1115: tradición hispanoamericana y filtros naturaleza/formato."""
from __future__ import annotations

from pathlib import Path

from zascarr.models import ComicTradition, IssueFormat, SeriesKind
from zascarr.web.library import (
    _FORMATO_LABEL,
    _NATURALEZA_LABEL,
    _TRADICION_LABEL,
    _leer_filtros,
    _qs,
)


def test_hispanoamericano_en_enum_y_etiqueta():
    assert ComicTradition.HISPANOAMERICANO.value == "hispanoamericano"
    assert _TRADICION_LABEL[ComicTradition.HISPANOAMERICANO] == "Hispanoamericano"


def test_naturaleza_y_formato_normalizan_y_url():
    f = _leer_filtros("1", "", "", "", "", "", "", "", "", "", naturaleza="annual",
                      formato="hardcover")
    assert f.naturaleza == SeriesKind.ANNUAL.value and f.formato == IssueFormat.HARDCOVER.value
    qs = _qs(f, page=1)
    assert "naturaleza=annual" in qs and "formato=hardcover" in qs
    malo = _leer_filtros("1", "", "", "", "", "", "", "", "", "", naturaleza="x",
                         formato="y")
    assert malo.naturaleza == "" and malo.formato == ""
    assert len(malo.avisos) == 2
    assert set(_NATURALEZA_LABEL) == {"regular", "annual", "special", "one_shot"}
    assert set(_FORMATO_LABEL) >= {"single_issue", "hardcover", "omnibus", "digital"}


def test_plantilla_selects_y_chips():
    panel = Path("src/zascarr/web/templates/_filtros_panel_campos.html").read_text()
    esc = Path("src/zascarr/web/templates/_escaparate.html").read_text()
    assert 'id="f-naturaleza"' in panel and 'name="naturaleza"' in panel
    assert 'id="f-formato"' in panel and 'name="formato"' in panel
    assert "naturaleza=regular" in esc and "naturaleza=one_shot" in esc
    assert "Tomo único" in Path("src/zascarr/web/library.py").read_text()


def test_filtros_en_pagina_y_fragmento_estaticos():
    panel = Path("src/zascarr/web/templates/_filtros_panel_campos.html").read_text()
    assert "{% for value, label in naturalezas %}" in panel
    assert "{% for value, label in formatos %}" in panel


def test_ssr_y_fragmento_con_naturaleza_y_formato():
    from tests.test_web_library import FakeExecResult, FakeSession, make_series, use_fake_session

    pagina_q = [FakeExecResult([]), FakeExecResult(1), FakeExecResult([make_series()])]
    with use_fake_session(FakeSession(pagina_q)) as client:
        r = client.get("/ui/biblioteca?naturaleza=annual&formato=hardcover")
    assert r.status_code == 200
    assert 'id="f-naturaleza"' in r.text and 'id="f-formato"' in r.text
    assert "Naturaleza: Anual" in r.text and "Formato: Tapa dura" in r.text

    fragmento_q = [FakeExecResult(1), FakeExecResult([make_series()])]
    with use_fake_session(FakeSession(fragmento_q)) as client:
        f = client.get("/ui/biblioteca/resultados?naturaleza=annual&formato=hardcover",
                       headers={"HX-Request": "true"})
    assert f.status_code == 200
    assert "naturaleza=annual" in f.headers["HX-Push-Url"]
    assert "formato=hardcover" in f.headers["HX-Push-Url"]


def test_escaparate_solo_limpio_con_naturaleza_y_formato():
    for kwargs in ({"naturaleza": "annual"}, {"formato": "hardcover"}):
        f = _leer_filtros("1", "", "", "", "", "", "", "", "", "", modo="escaparate",
                          **kwargs)
        assert f.modo == "gestion"
    limpio = _leer_filtros("1", "", "", "", "", "", "", "", "", "", modo="escaparate")
    assert limpio.modo == "escaparate"


def test_accesos_naturaleza_sin_duplicados():
    esc = Path("src/zascarr/web/templates/_escaparate.html").read_text()
    for clave in ("regular", "annual", "special", "one_shot"):
        assert esc.count(f"naturaleza={clave}") == 1


def test_panel_filtros_se_coloca_y_cierra():
    js = Path("src/zascarr/static/biblioteca-filtros.js").read_text()
    assert "getBoundingClientRect().bottom" in js
    assert 'panel.querySelector(".barra-panel-campos")' in js
    assert 'addEventListener("htmx:afterSwap", colocar)' in js
    assert 'evento.key !== "Escape"' in js
    assert "panel.contains(evento.target)" in js
    bib = Path("src/zascarr/web/templates/biblioteca.html").read_text()
    assert "biblioteca-filtros.js" in bib
