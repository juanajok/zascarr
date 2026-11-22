"""Regresión: hallazgos del benchmark de calidad de la interfaz (2026-11-22).

Ficha: `docs/design/benchmark-calidad-front.md`. Los hallazgos 2, 4 y 13 los cubre la prueba de
estructura de pantallas (`test_estructura_pantallas_pg.py`); el 8, `test_web_navegacion`; el 9,
`test_web_lectura`.
"""
from __future__ import annotations

import re
from pathlib import Path

from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"


def plantilla(nombre: str) -> str:
    return (PLANTILLAS / nombre).read_text(encoding="utf-8")


def regla(selector: str) -> str:
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert m, f"no existe la regla {selector} en web.css"
    return m.group(1)


def test_1_ajustes_no_se_ensancha_por_un_desplegable_ni_una_ruta():
    """A 320 px Ajustes se salía 54 px: `fieldset` mide como su contenido más ancho por defecto."""
    assert ".ajustes-card { min-inline-size: 0; overflow-wrap: anywhere; }" in CSS
    assert "max-width: 100%" in regla(".ajustes-card select")


def _render(fuente: str, **ctx) -> str:
    return crear_templates().env.from_string(fuente).render(**ctx)


def test_3_el_campo_con_error_se_liga_a_su_mensaje_y_recibe_el_foco_el_primero():
    fuente = ('{% set orden_campos = ["a", "b"] %}'
              '<input name="a"{{ ui.invalido(errores, "a", orden_campos) }}>'
              '<input name="b"{{ ui.invalido(errores, "b", orden_campos) }}>')
    html = _render(fuente, errores={"b": "Mal", "general": "x"})
    assert '<input name="a">' in html
    assert ('<input name="b" id="campo-b" aria-invalid="true" aria-describedby="error-b" '
            'autofocus>') in html
    dos = _render(fuente, errores={"a": "Mal", "b": "Mal"})
    # Con dos errores el foco va al resumen de errores (`ui.resumen_errores`), no a un campo.
    assert dos.count("aria-invalid") == 2 and dos.count("autofocus") == 0
    assert _render(fuente, errores={}).count("aria-") == 0


def test_3_los_formularios_de_edicion_usan_la_macro_y_el_id_del_error():
    for nombre in ("editar_serie.html", "editar_numero.html", "editar_arco.html", "arco.html"):
        texto = plantilla(nombre)
        campos = re.findall(r'\{% if errores\.(\w+) %\}<span class="campo-error"', texto)
        assert campos, nombre
        for campo in campos:
            assert f'id="error-{campo}"' in texto, (nombre, campo)
            assert f'name="{campo}"{{{{ ui.invalido(errores, "{campo}", orden_campos' in texto


def test_5_sin_botones_desactivados_sin_explicacion():
    asociar = plantilla("asociar_fuente.html")
    assert "<script>" not in asociar
    assert re.search(r'id="buscar-asociar" type="submit">', asociar)
    previa = plantilla("enriquecimiento_previa.html")
    assert "disabled" not in previa
    assert "No hay nada que aplicar" in previa


def test_6_las_rejillas_de_portadas_cargan_en_diferido_tras_la_primera_fila():
    assert 'carga="lazy" if loop.index > 12 else none' in plantilla("_rejilla_biblioteca.html")
    escaparate = plantilla("_escaparate.html")
    assert escaparate.count('carga="lazy"') == 3
    assert 'carga="lazy" if loop.index > 6 else none' in escaparate


def test_10_los_enlaces_a_otra_pestana_lo_avisan_y_llevan_rel():
    for ruta in PLANTILLAS.glob("*.html"):
        texto = ruta.read_text(encoding="utf-8")
        for enlace in re.findall(r'<a [^>]*target="_blank"[^>]*>', texto):
            assert "noopener" in enlace, (ruta.name, enlace)
