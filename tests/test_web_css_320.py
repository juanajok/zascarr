"""#1121 (UXA-04): Ajustes y la ficha de serie caben a 320 px y sus resúmenes son operables.

Mecanismo de cada fallo medido en navegador (320 px, datos poblados):
  · Ajustes llegaba a 336 px: una dirección larga en un `<code>` de las ayudas no se partía.
  · La ficha de serie llegaba a 465 px: `.chip` era `nowrap` y el nombre largo de una editorial
    no cabía.
  · Los resúmenes de las ayudas de Ajustes medían 22 px en escritorio (WCAG 2.5.8 pide 24; el
    contrato local, 40; en táctil ya llegan a 44 por la regla final de `web.css`).
La medición completa vive en el PR; aquí se fija el mecanismo, sin navegador.
"""
from __future__ import annotations

import re

from tests.test_web_css_contraste import _reglas


def _regla(selector: str) -> dict[str, str]:
    return next(d for s, d in _reglas() if s == selector)


def test_un_chip_con_un_nombre_largo_se_parte_en_vez_de_ensanchar_la_pagina():
    chip = _regla(".chip")
    assert chip.get("white-space") == "normal"
    assert chip.get("overflow-wrap") == "anywhere"
    assert chip.get("max-width") == "100%"


def test_una_direccion_larga_en_una_ayuda_de_ajustes_se_parte():
    assert _regla(".ajustes-hint code").get("overflow-wrap") == "anywhere"


def test_los_resumenes_de_las_ayudas_de_ajustes_miden_40_px_tambien_en_escritorio():
    resumen = next(d for s, d in _reglas() if s == ".ajustes-mas summary" and "min-height" in d)
    minimo = float(re.match(r"(\d+(?:\.\d+)?)px", resumen["min-height"]).group(1))
    assert minimo >= 40
