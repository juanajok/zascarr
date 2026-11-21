"""Regresión: la fila horizontal de la cola de pendientes no se hereda en los demás paneles.

`.pending-card` es la tarjeta de la cola de «Por revisar», pero también el panel de Estado
(comprobaciones y cortesía), de las fichas de datos y de Sueltos. La lista compacta de pendientes
(2026-11-17) puso `flex-direction: row` en la regla general y la tabla de comprobaciones de /estado
salió en una sola línea apretada («Base / de / datos»). La fila va solo dentro de `.pending-grid`.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"


def regla(selector: str) -> str:
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert m, f"no existe la regla {selector} en web.css"
    return m.group(1)


def test_el_panel_general_apila_en_columna():
    assert "flex-direction: column" in regla(".pending-card")
    assert "flex-direction: row" not in regla(".pending-card")


def test_la_fila_es_solo_de_la_cola():
    assert "flex-direction: row" in regla(".pending-grid .pending-card")


def test_la_tarjeta_de_la_cola_vive_dentro_de_pending_grid():
    texto = (PLANTILLAS / "pendientes.html").read_text(encoding="utf-8")
    lista = texto[texto.index('<ul class="pending-grid"'):]
    assert '{% include "_tarjeta_pendiente.html" %}' in lista


def test_estado_monta_las_comprobaciones_en_un_pending_card():
    # Si este marcado cambia, el caso que motivó la regla ya no se cubre aquí.
    texto = (PLANTILLAS / "estado.html").read_text(encoding="utf-8")
    assert 'class="pending-card estado-checks"' in texto


def test_el_resumen_de_estado_declara_su_propia_fila():
    # Es un `.pending-card` con el punto a la izquierda del texto: no depende de la regla general.
    assert "flex-direction: row" in regla(".estado-summary")
