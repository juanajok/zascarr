"""Regresión: «Actualizar la biblioteca» cuadra con la cabecera de Biblioteca.

Tras #1164 el botón medía 44 px en escritorio (un `min-height` propio) frente a los 40 px de los
botones de la cabecera y la franja ocupaba cuatro filas sueltas con huecos distintos (#1173). Ya
cuadrado, seguía descolocado: era la única acción a la izquierda, en una fila propia, encima de las
pestañas «Gestión / Escaparate» y con su mismo aspecto. El botón va ahora con las acciones de la
cabecera y la línea de estado, bajo la frase de entrada.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"
PLANTILLA = (PLANTILLAS / "_actualizar_biblioteca.html").read_text(encoding="utf-8")
BIBLIOTECA = (PLANTILLAS / "biblioteca.html").read_text(encoding="utf-8")


def bloque_franja() -> str:
    inicio = CSS.index("/* #1160:")
    return CSS[inicio:CSS.index(".barra-biblioteca {", inicio)]


def test_el_boton_no_fuerza_un_alto_ni_un_ancho_propios():
    assert "min-height" not in bloque_franja()
    assert "width: 100%" not in bloque_franja()


def test_el_boton_va_con_las_acciones_de_la_cabecera():
    acciones = BIBLIOTECA.split('<div class="biblioteca-acciones">', 1)[1].split("</div>", 1)[0]
    assert 'id="actualizar-boton"' in acciones
    assert acciones.index("actualizar-boton") < acciones.index("/ui/mejoras")


def test_el_boton_tiene_el_aspecto_de_sus_vecinos():
    for fuente in (BIBLIOTECA, PLANTILLA):
        boton = fuente.split('id="actualizar-boton"', 1)[1].split(">", 1)[0]
        assert 'class="btn ghost sm biblioteca-accion"' in boton


def test_la_linea_de_estado_vive_en_la_cabecera_bajo_la_frase():
    cabecera = BIBLIOTECA.split("</header>", 1)[0]
    assert 'id="actualizar-biblioteca"' in cabecera
    assert '"estado estado"' in CSS
    m = re.search(r"(?m)^\.biblioteca-actualizar \{([^}]*)\}", CSS)
    assert m and "grid-area: estado" in m.group(1)


def test_al_cargar_el_bloque_trae_el_estado_del_boton_fuera_de_banda():
    completo = PLANTILLA.split("{% else %}\n<section", 1)[1]
    assert "{{ boton(oob=true) }}" in completo


def test_la_linea_no_tiene_hueco_de_fila():
    # Un hueco de fila separaría la región viva vacía, que siempre está, y descuadraría el ritmo.
    m = re.search(r"(?m)^\.biblioteca-actualizar \{([^}]*)\}", CSS)
    assert m and "display: flex" in m.group(1) and "column-gap" in m.group(1)
    assert not re.search(r"(?<!column-)gap:", m.group(1))


def test_los_avisos_van_debajo_de_la_linea_y_que_mira_en_ella():
    seccion = PLANTILLA[PLANTILLA.index("<section"):]
    assert seccion.index("biblioteca-actualizar-detalle") < seccion.index("region()")
