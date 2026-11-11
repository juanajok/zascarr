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
    assert 'id="contador-texto" hx-swap-oob="true"' in html
    assert "2 series" in html
    assert "2 series coinciden con estos filtros." in html
    assert 'id="cuenta-filtros" hx-swap-oob="true">Filtros (1)' in html
    assert 'id="control-vista"' in html
    control = html[html.index('id="control-vista"'):]
    control = control[:control.index("</a>")]
    assert 'hx-swap-oob="true"' in control
    assert 'id="filtros-campos" class="barra-panel-campos" hx-swap-oob="true"' in html


def test_cuenta_de_filtros_no_incluye_busqueda_orden_ni_vista():
    html = _index(path="/ui/biblioteca?q=alfa&tradition=tebeo&orden=reciente&vista=lista")
    assert "Filtros (2)" in html


def test_limpiar_filtros_conserva_orden_y_vista():
    html = _index(path="/ui/biblioteca?tradition=tebeo&orden=reciente&vista=lista")
    assert 'href="/ui/biblioteca?orden=reciente&amp;vista=lista&amp;page=1"' in html
    assert "Limpiar filtros" in html


def test_css_de_barra_compacta_y_44_px():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".barra-biblioteca {" in css
    assert "border: 3px solid var(--ink);" in css
    assert "background: var(--paper-2);" in css
    assert ".barra-busqueda { flex: 1 1 320px; max-width: 560px;" in css
    assert ".barra-acciones { display: flex; flex-wrap: wrap; align-items: center;" in css
    assert "margin-left: auto;" in css
    assert ".barra-acciones > * { min-height: 44px; }" in css
    assert "min-height: 44px" in css
    assert "max-height: calc(100dvh - 8.5rem)" in css


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


def test_oob_incluye_campos_del_panel_para_no_resucitar_filtros():
    html = _index(path="/ui/biblioteca/resultados?quitar=todos&tradicion=&orden=reciente&vista=lista")
    assert 'id="filtros-campos" class="barra-panel-campos" hx-swap-oob="true"' in html
    for campo in ("f-tradition", "f-publisher", "f-leido", "f-personaje", "f-saga", "f-etiquetas"):
        assert f'id="{campo}"' in html
    assert 'id="control-vista"' in html
    control = html[html.index('id="control-vista"'):]
    control = control[:control.index("</a>")]
    assert 'hx-swap-oob="true"' in control


def test_formulario_conserva_vista_y_no_revierte_a_tarjetas():
    html = _index(path="/ui/biblioteca?vista=lista&orden=reciente")
    assert '<input type="hidden" id="f-vista" name="vista" value="lista">' in html
    assert "value=\"reciente\" selected" in html


def test_css_objetivos_tactiles_y_panel_ancho_completo():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".barra-busqueda input[type=\"search\"] { width: 100%; min-height: 44px; }" in css
    assert ".barra-panel-campos .series-results a { min-height: 44px;" in css
    assert ".faceta-etiqueta a { font-size: .875rem; min-height: 44px;" in css
    assert "min-height: 44px" in css.split(".quitar-filtro,", 1)[1][:160]
    assert ".barra-panel { min-width: 0; position: relative; }" in css
    assert ".barra-panel-campos {" in css
    assert "top: calc(100% + 8px);" in css and "right: 0;" in css
    assert "max-height: calc(100dvh - 8.5rem)" in css
    assert ".barra-biblioteca .barra-panel-campos select" in css
    assert "max-width: none; width: 100%;" in css


def test_flujo_vista_lista_cambiar_orden_conserva_vista():
    # Fragmento tras cambiar de vista: el hidden y el control se actualizan por OOB.
    fragmento = _index(path="/ui/biblioteca/resultados?vista=lista&orden=reciente")
    assert '<input type="hidden" id="f-vista" name="vista" value="lista" hx-swap-oob="true">' in fragmento
    assert 'id="control-vista"' in fragmento
    # Página completa equivalente: el form lleva vista=lista.
    pagina = _index(path="/ui/biblioteca?vista=lista&orden=reciente")
    assert '<input type="hidden" id="f-vista" name="vista" value="lista">' in pagina


def test_css_panel_absoluto_tambien_en_movil_y_tactil_ancho():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    bloque = css.split("@media (max-width: 640px)", 1)[1].split("@media (max-width: 360px)", 1)[0]
    assert "position: fixed" in bloque and "bottom: 64px" in bloque
    assert "left: 0" in bloque and "right: 0" in bloque
    assert ".faceta-etiqueta a { font-size: .875rem; min-height: 44px; min-width: 44px;" in css
    assert "min-width: 44px" in css.split(".quitar-filtro,", 1)[1][:200]


def test_flujo_htmx_vista_y_luego_orden_usa_el_hidden_actualizado():
    import re
    # Página inicial (tarjetas) y fragmento al cambiar a lista.
    pagina = _index(path="/ui/biblioteca")
    fragmento = _index(path="/ui/biblioteca/resultados?vista=lista")
    hidden_oob = re.search(r'<input[^>]*id="f-vista"[^>]*hx-swap-oob="true"[^>]*>', fragmento)
    assert hidden_oob is not None
    # htmx sustituye el hidden fuera de #rejilla; simulamos ese paso y comprobamos
    # que el siguiente cambio (orden) envía vista=lista.
    pagina_tras_swap = re.sub(
        r'<input[^>]*id="f-vista"[^>]*>', hidden_oob.group(0), pagina, count=1)
    assert 'id="f-vista" name="vista" value="lista"' in pagina_tras_swap


def test_barra_es_un_panel_con_busqueda_acotada_y_acciones_a_la_derecha():
    from pathlib import Path
    html = _index()
    assert '<form id="filtros" class="barra-biblioteca"' in html
    assert '<div class="barra-busqueda">' in html
    assert '<div class="barra-acciones">' in html
    assert 'class="contador-resumen" role="status"' in html
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".barra-biblioteca {" in css and "border: 3px solid var(--ink);" in css
    assert "padding: 10px 12px;" in css
    assert "background: var(--paper-2);" in css
    assert ".barra-busqueda { flex: 1 1 320px; max-width: 560px;" in css
    assert ".barra-acciones { display: flex; flex-wrap: wrap; align-items: center;" in css
    assert "margin-left: auto;" in css


def test_summary_es_un_boton_con_chevron_y_estado_abierto():
    from pathlib import Path
    html = _index()
    assert '<summary class="barra-panel-boton"' in html
    assert 'aria-controls="filtros-campos"' in html
    assert 'class="barra-panel-chevron"' in html
    assert "m6 9 6 6 6-6" in html  # chevron-down de Lucide
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".barra-panel-boton {" in css
    assert "border: 2px solid var(--ink);" in css
    assert "border-radius: var(--radius-pill);" in css
    assert "box-shadow: var(--shadow-ink-sm);" in css
    assert ".barra-panel[open] > .barra-panel-boton { background: var(--ink); color: var(--paper); }" in css


def test_vista_es_segmentada_con_aria_current_y_oob():
    html = _index()
    assert '<div id="control-vista" class="barra-vista" role="group"' in html
    assert html.count('class="barra-vista-opcion') == 2
    assert 'aria-current="page"' in html
    assert ">Tarjetas</span>" in html and ">Lista</span>" in html
    fragmento = _index(path="/ui/biblioteca/resultados?vista=lista")
    control = fragmento[fragmento.index('id="control-vista"'):]
    control = control[:control.index("</div>")]
    assert 'hx-swap-oob="true"' in control
    assert 'aria-current="page"' in control
    assert "barra-vista-opcion-actual" in control


def test_orden_tiene_etiqueta_visible_y_opciones_cortas():
    html = _index(path="/ui/biblioteca?orden=reciente")
    assert '<label for="f-orden">Orden</label>' in html
    assert 'value="reciente" selected' in html
    for opcion in (">A-Z</option>", ">Z-A</option>", ">Recientes</option>",
                   ">Antiguas</option>", ">Añadidas</option>"):
        assert opcion in html
    assert "Ordenar por</label>" not in html


def test_alturas_44_y_movil_sin_contador_en_la_barra():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    for selector in (".barra-contador {", ".barra-panel-boton {", ".barra-orden select {",
                     ".barra-vista-opcion {"):
        bloque = css.split(selector, 1)[1].split("}", 1)[0]
        assert "min-height: 44px" in bloque, selector
    assert ".barra-acciones > * { min-height: 44px; }" in css
    assert ".contador-resumen { display: none; }" in css
    assert "@media (max-width: 480px)" in css
    assert ".barra-contador { display: none; }" in css
    assert ".contador-resumen {" in css and "display: block;" in css


def test_cabecera_accion_es_boton_y_no_enlace_subrayado():
    from pathlib import Path
    html = _index()
    assert 'class="btn ghost sm biblioteca-accion"' in html
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert ".biblioteca-cabecera .biblioteca-accion {" in css
    assert "text-decoration: none;" in css
    assert "grid-template-areas: \"titulo accion\" \"subtitulo subtitulo\";" in css
