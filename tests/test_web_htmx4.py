"""htmx 4: los atributos retirados de htmx 2 no deben volver a las plantillas."""
from __future__ import annotations

from pathlib import Path

PLANTILLAS = Path(__file__).resolve().parents[1] / "src/zascarr/web/templates"

def test_no_queda_hx_disabled_elt_en_plantillas():
    restos = [p.name for p in PLANTILLAS.glob("*.html") if "hx-disabled-elt" in p.read_text()]
    assert restos == []

def test_los_formularios_que_se_deshabilitan_usan_hx_disable():
    texto = "".join(p.read_text() for p in PLANTILLAS.glob("*.html"))
    assert 'hx-disable="find button"' in texto
