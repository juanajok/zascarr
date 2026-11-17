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


def _cliente_pagina():
    from tests.test_web_library import FakeExecResult, FakeSession, make_series, use_fake_session
    return use_fake_session(FakeSession([
        FakeExecResult([]), FakeExecResult(1), FakeExecResult([make_series()])
    ]))


def _cliente_fragmento():
    from tests.test_web_library import FakeExecResult, FakeSession, make_series, use_fake_session
    return use_fake_session(FakeSession([
        FakeExecResult(1), FakeExecResult([make_series()])
    ]))


def test_ssr_y_fragmento_con_densidad():
    with _cliente_pagina() as client:
        pagina = client.get("/ui/biblioteca")
    with _cliente_fragmento() as client:
        fragmento = client.get(
            "/ui/biblioteca/resultados?densidad=compacta&q=Batman&orden=reciente&page=1",
            headers={"HX-Request": "true"})
    assert pagina.status_code == fragmento.status_code == 200
    assert "control-densidad" in pagina.text and "library-grid-intermedia" in pagina.text
    assert "library-grid-compacta" in fragmento.text
    assert 'hx-swap-oob="true"' in fragmento.text and "control-densidad" in fragmento.text
    assert "q=Batman" in fragmento.headers["HX-Push-Url"]
    assert "orden=reciente" in fragmento.headers["HX-Push-Url"]
    assert "densidad=compacta" in fragmento.headers["HX-Push-Url"]


def test_modo_escaparate_avisa_en_pagina_y_fragmento():
    with _cliente_pagina() as client:
        pagina = client.get("/ui/biblioteca?modo=escaparate")
    with _cliente_fragmento() as client:
        fragmento = client.get("/ui/biblioteca/resultados?modo=escaparate",
                               headers={"HX-Request": "true"})
    assert "escaparate" in pagina.text.lower()
    assert "escaparate" in fragmento.text.lower()


def test_densidad_tactil_44_y_js_atajo():
    css = Path("src/zascarr/static/web.css").read_text()
    js = Path("src/zascarr/static/biblioteca-atajo.js").read_text()
    assert ".barra-densidad-opcion" in css
    # La regla de densidad debe declarar 44 px para táctil.
    inicio = css.index(".barra-densidad-opcion")
    assert "min-height: 44px" in css[inicio:inicio + 250]
    assert "preventDefault" in js and "isContentEditable" in js


def test_chips_ficha_y_control_visible():
    ficha = Path("src/zascarr/web/templates/series_detail.html").read_text()
    css = Path("src/zascarr/static/web.css").read_text()
    control = Path("src/zascarr/web/templates/_control_vista.html").read_text()
    assert 'publisher_id={{ series.publisher.id }}' in ficha
    assert 'hx-get="/ui/biblioteca/resultados?publisher_id=' in ficha
    assert 'author_id={{ a.id }}' in ficha
    assert "barra-densidad-texto" in control
    assert ".barra-vista-texto { display: none; }" in css
    assert ".barra-densidad-texto { display: inline; }" in css
