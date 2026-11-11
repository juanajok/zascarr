# ruff: noqa: E501
"""BL-INF11 (#628): URL y selector del orden de Biblioteca."""
from __future__ import annotations

from zascarr.web.library import Filtros, _leer_filtros, _url_fragmento, _url_pagina


def test_orden_valido_y_url_conserva_filtros_y_resetea_pagina():
    f = _leer_filtros("3", "bat", "", "", "", "", "", "", "si", "reciente")
    assert f.orden == "reciente"
    url = _url_pagina(f, page=1)
    assert "orden=reciente" in url and "page=1" in url
    for trozo in ("q=bat", "leido=si"):
        assert trozo in url
    assert "page=3" not in url
    assert "orden=reciente" in _url_fragmento(f, page=1)


def test_orden_invalido_o_vacio_cae_al_defecto_sin_aviso():
    for valor in ("", "otro", "  "):
        f = _leer_filtros("1", "", "", "", "", "", "", "", "", valor)
        assert f.orden == "titulo"
        assert not any("orden" in a.lower() for a in f.avisos)


def test_orden_por_defecto_no_ensucia_la_url():
    f = Filtros()
    assert f.orden == "titulo"
    assert "orden=" not in _url_pagina(f, page=1)


def test_vista_y_orden_coexisten():
    f = _leer_filtros("2", "", "", "", "", "", "lista", "", "", "anio_desc")
    url = _url_pagina(f, page=1)
    assert "vista=lista" in url and "orden=anio_desc" in url


def test_selector_renderiza_label_y_opcion_elegida():
    from tests.test_web_library import FakeExecResult, FakeSession, make_series, use_fake_session

    session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([make_series()])])
    with use_fake_session(session) as client:
        r = client.get("/ui/biblioteca?orden=reciente&q=Batman")
    assert r.status_code == 200
    assert 'for="f-orden">Ordenar por</label>' in r.text
    assert 'id="f-orden"' in r.text
    assert 'value="reciente" selected' in r.text
    assert "Añadidas" in r.text
    assert "Aplicar orden" not in r.text


def test_url_conserva_todos_los_filtros_y_vista():
    f = _leer_filtros("4", "bat", "franco_belgian", "11111111-1111-1111-1111-111111111111",
                      "22222222-2222-2222-2222-222222222222",
                      "33333333-3333-3333-3333-333333333333", "lista", "etiqueta", "leyendo",
                      "anio_asc")
    url = _url_pagina(f, page=1)
    for trozo in ("q=bat", "tradition=franco_belgian", "publisher_id=11111111",
                  "character_id=22222222", "story_arc_id=33333333", "etiquetas=etiqueta",
                  "leido=leyendo", "vista=lista", "orden=anio_asc", "page=1"):
        assert trozo in url
