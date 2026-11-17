# ruff: noqa: E501
"""#360: foco, avisos y título del asistente de vinculación (plantillas)."""
from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
T = RAIZ / "src/zascarr/web/templates"
CSS = (RAIZ / "src/zascarr/static/web.css").read_text(encoding="utf-8")


def test_la_accion_tiene_foco_programatico_y_no_es_region_viva_anidada():
    t = (T / "_vinculacion_revision.html").read_text(encoding="utf-8")
    assert '<div class="vinc-accion-resultado" tabindex="-1" autofocus' in t
    assert 'vinc-accion-resultado" role="status"' not in t
    assert "ui.aviso(accion.tipo, accion.texto, viva=false)" in t


def test_el_resultado_recibe_el_foco_solo_en_la_respuesta_htmx():
    t = (T / "_vinculacion_resultado.html").read_text(encoding="utf-8")
    assert '<h3 id="res-resultado" class="titulo-frase"{% if foco_resultado %} tabindex="-1" autofocus{% endif %}>' in t
    assert '<h3 id="res-fallo" class="titulo-frase"{% if foco_resultado %} tabindex="-1" autofocus{% endif %}>' in t


def test_el_fragmento_htmx_lleva_titulo_de_resultado():
    t = (T / "_vinculacion_resultado.html").read_text(encoding="utf-8")
    assert '{% if oob_cabecera %}<title>Resultado de la vinculación — ZascArr</title>' in t


def test_la_pagina_titula_revision_y_resultado():
    t = (T / "asistente_vinculacion.html").read_text(encoding="utf-8")
    assert "titulo_vinculacion(resultado)" in t
    m = (T / "_asistente_macros.html").read_text(encoding="utf-8")
    assert "Resultado de la vinculación — ZascArr" in m
    assert "Revisar selección y números — ZascArr" in m


def test_el_paso_3_se_llama_vincular_y_ver_el_resultado_en_todas_las_pantallas():
    m = (T / "_asistente_macros.html").read_text(encoding="utf-8")
    assert '(3, "Vincular y ver el resultado")' in m
    assert '(3, "Vincular")' not in m


def test_el_indicador_alinea_el_circulo_con_la_primera_linea():
    assert ".pasos-asistente li { display: flex; align-items: flex-start;" in CSS
    assert "align-items: center" not in CSS.split(".pasos-asistente li {", 1)[1].split("}", 1)[0]
