# ruff: noqa: E501
"""#1080: plantilla/CSS de listas (formularios, 44 px y target del detalle)."""
from __future__ import annotations

from pathlib import Path


def test_formularios_apilados_y_44():
    listas = Path("src/zascarr/web/templates/listas.html").read_text()
    detalle = Path("src/zascarr/web/templates/lista_detalle.html").read_text()
    css = Path("src/zascarr/static/web.css").read_text()
    assert "formulario-listas" in listas and "formulario-listas" in detalle
    assert ".formulario-listas { display: grid;" in css
    assert ".formulario-listas input, .formulario-listas textarea, .formulario-listas select { width: 100%; min-height: 44px;" in css
    assert ".formulario-listas .btn { min-height: 44px;" in css
    assert ".lista-item-acciones" in css and "min-height: 44px" in css
    assert "@media (max-width: 480px) { .lista-item-acciones" in css


def test_detalle_de_issue_apunta_al_hijo_y_cierra():
    t = Path("src/zascarr/web/templates/issue_detail.html").read_text()
    detalles = t.split('class="anadir-a-lista"', 1)[1].split("</details>", 1)[0]
    assert 'hx-target="#lista-opciones"' in detalles
    assert 'id="lista-opciones"' in detalles
    assert 'hx-target="this"' not in detalles
    assert "<summary" in detalles


def test_acciones_de_fila_agrupadas():
    detalle = Path("src/zascarr/web/templates/lista_detalle.html").read_text()
    assert 'class="lista-item-acciones"' in detalle
    assert detalle.count('class="lista-item-acciones"') == detalle.count("{% for x in items %}")


def test_acciones_sueltas_a_44_px():
    from pathlib import Path as _P
    css = _P("src/zascarr/static/web.css").read_text()
    assert ".lista-borrar .btn" in css and ".lista-opciones-gestion .btn" in css
    assert "lista-opciones-gestion" in _P("src/zascarr/web/templates/_lista_opciones.html").read_text()
