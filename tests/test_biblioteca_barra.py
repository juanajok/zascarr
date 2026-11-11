# ruff: noqa: E501
"""Biblioteca: barra única, contador OOB, panel y limpiar (rebanada 1)."""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.test_web_library import (
    FakeExecResult,
    FakeSession,
    make_series,
    override_get_db,
)
from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import Publisher


def _index(path="/ui/biblioteca"):
    editorial = Publisher(id=uuid4(), name="Bruguera")
    if path.startswith("/ui/biblioteca/resultados"):
        cola = [FakeExecResult(2),
                FakeExecResult([make_series("Alfa"), make_series("Beta")])]
    else:
        cola = [FakeExecResult([editorial]), FakeExecResult(2),
                FakeExecResult([make_series("Alfa"), make_series("Beta")])]
    session = FakeSession(cola)
    app.dependency_overrides[get_db] = override_get_db(session)
    try:
        client = TestClient(app, base_url="http://localhost",
                            headers={"Origin": "http://localhost"})
        return client.get(path).text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_barra_unica_con_busqueda_acciones_y_panel():
    html = _index()
    assert "barra-buscar" not in html  # no existe una segunda barra de búsqueda
    assert 'class="barra-busqueda"' in html
    assert 'class="barra-acciones"' in html
    assert 'id="panel-filtros"' in html
    assert 'id="f-orden"' in html
    assert 'class="barra-vista"' in html
    assert "Buscar por título" in html


def test_panel_tiene_labels_visibles_y_los_seis_filtros():
    html = _index()
    panel = html[html.index('id="panel-filtros"'):]
    panel = panel[:panel.index("</details>")]
    for etiqueta, campo in (
        ("Tradición", "f-tradition"), ("Editorial", "f-publisher"),
        ("Lectura", "f-leido"), ("Personaje", "f-personaje"),
        ("Saga", "f-saga"), ("Etiquetas", "f-etiquetas"),
    ):
        assert f'<label for="{campo}">{etiqueta}</label>' in panel
    assert "<noscript>" in panel and "Aplicar filtros" in panel


def test_fragmento_actualiza_contador_y_cuenta_por_oob():
    html = _index(path="/ui/biblioteca/resultados?tradition=tebeo&orden=reciente")
    assert 'id="contador-biblioteca"' in html
    assert 'hx-swap-oob="true"' in html
    assert "2 series" in html
    assert "2 series coinciden con estos filtros." in html
    assert 'id="cuenta-filtros" hx-swap-oob="true">Filtros (1)' in html


def test_cuenta_de_filtros_no_incluye_busqueda_orden_ni_vista():
    html = _index(path="/ui/biblioteca?q=alfa&tradition=tebeo&orden=reciente&vista=lista")
    assert "Filtros (1)" in html
    assert "Filtros (2)" not in html


def test_limpiar_filtros_conserva_orden_y_vista():
    html = _index(path="/ui/biblioteca?tradition=tebeo&orden=reciente&vista=lista")
    assert 'href="/ui/biblioteca?orden=reciente&amp;vista=lista&amp;page=1"' in html
    assert "Limpiar filtros" in html


def test_css_de_barra_compacta_y_44_px():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".barra-acciones { display: flex; flex-wrap: nowrap;" in css
    assert "min-height: 44px" in css
    assert ".barra-panel-campos" in css and "max-height: 70vh" in css


def test_panel_conserva_los_tres_buscadores_y_sus_endpoints():
    html = _index()
    panel = html[html.index('id="panel-filtros"'):]
    panel = panel[:panel.index("</details>")]
    assert 'hx-get="/ui/biblioteca/etiquetas/sugerir"' in panel
    assert 'hx-target="#sugerencias-etiquetas"' in panel
    assert 'hx-get="/ui/biblioteca/buscar-personaje"' in panel
    assert 'hx-target="#resultados-personaje"' in panel
    assert 'hx-get="/ui/biblioteca/buscar-saga"' in panel
    assert 'hx-target="#resultados-saga"' in panel
    assert 'hx-include="#filtros"' in panel
    assert 'aria-live="polite"' in panel


def test_abrir_el_panel_es_nativo_y_no_roba_el_foco():
    html = _index()
    panel = html[html.index('id="panel-filtros"'):]
    panel = panel[:panel.index("</details>")]
    assert "<summary" in panel
    assert 'aria-controls="filtros-campos"' in panel
    assert "autofocus" not in panel
    assert "onclick=" not in panel and "hx-confirm" not in panel
