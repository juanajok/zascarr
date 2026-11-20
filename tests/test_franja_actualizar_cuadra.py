"""Regresión: la franja «Actualizar la biblioteca» cuadra con la cabecera de Biblioteca.

Tras #1164 el botón medía 44 px en escritorio (un `min-height` propio) frente a los 40 px de los
botones de la cabecera, la franja ocupaba cuatro filas sueltas con huecos distintos y en el móvil
el botón iba a todo el ancho mientras los vecinos se ajustaban a su texto. El alto táctil lo pone
la regla general de pantallas estrechas y táctiles; la franja no lo fuerza.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"
PLANTILLA = (PLANTILLAS / "_actualizar_biblioteca.html").read_text(encoding="utf-8")


def bloque_franja() -> str:
    inicio = CSS.index("/* #1160:")
    return CSS[inicio:CSS.index(".barra-biblioteca {", inicio)]


def test_el_boton_no_fuerza_un_alto_propio_en_escritorio():
    assert "min-height" not in bloque_franja()


def test_en_el_movil_el_boton_se_ajusta_a_su_texto_como_los_de_la_cabecera():
    assert "width: 100%" not in bloque_franja()


def test_la_franja_es_una_sola_fila_sin_hueco_de_fila():
    # Un hueco de fila separaría la región viva vacía, que siempre está, y descuadraría el ritmo.
    m = re.search(r"(?m)^\.biblioteca-actualizar \{([^}]*)\}", CSS)
    assert m and "display: flex" in m.group(1) and "column-gap" in m.group(1)
    assert not re.search(r"(?<!column-)gap:", m.group(1))


def test_los_avisos_van_debajo_de_la_linea_y_que_mira_en_ella():
    seccion = PLANTILLA[PLANTILLA.index("<section"):]
    assert seccion.index("biblioteca-actualizar-detalle") < seccion.index("region()")
