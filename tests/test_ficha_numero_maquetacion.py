"""Regresión: maquetación de la ficha de número (revisión del 2026-11-20).

1. Las acciones de la cabecera iban en tres filas: «Añadir a una lista» en otra y «Buscar una
   edición mejor» en una tercera, corrida 6 px (`.inline-desbloquear`), y «Leer», sin `.sm`, quedaba
   1 px más baja. Ahora son una sola fila, con el aspecto de las de Biblioteca.
2. El título bajaba 21 px respecto a la portada (margen del `h1`) y la portada llevaba un pie que
   no decía nada («Portada del número»).
3. En «Tu lectura», la etiqueta «Nota corta» quedaba al final de la fila de estados, lejos de su
   caja, y el límite de caracteres competía con el botón; la garantía quedaba fuera del formulario.
4. Dos cajas amarillas en «Tu lectura»: la ayuda pasa a texto secundario y el amarillo queda para la
   garantía junto a la acción (decisión del PO del 2026-11-20, que revisa en esto la de #1119).
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"
FICHA = (PLANTILLAS / "issue_detail.html").read_text(encoding="utf-8")
LECTURA = (PLANTILLAS / "_lectura_control.html").read_text(encoding="utf-8")


def regla(selector: str) -> str:
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert m, f"no existe la regla {selector} en web.css"
    return m.group(1)


def acciones() -> str:
    return FICHA.split('<div class="issue-acciones">', 1)[1].split("</details>", 1)[0]


def test_todas_las_acciones_van_en_una_fila():
    bloque = acciones()
    for texto in ("Leer", "Editar el número", "Completar datos", "Buscar una edición mejor",
                  "Añadir a una lista"):
        assert texto in bloque, texto
    assert "display: flex" in regla(".issue-acciones")


def test_ninguna_accion_va_corrida_ni_con_otro_alto():
    assert "inline-desbloquear" not in acciones()
    assert 'class="btn primary sm"' in acciones()


def test_leer_es_la_principal_y_va_primero():
    bloque = acciones()
    assert bloque.count("primary") == 1
    assert bloque.index("primary") < bloque.index("Editar el número")


def test_la_lista_se_abre_debajo_sin_mover_la_fila():
    assert "position: absolute" in regla(".issue-acciones .anadir-a-lista > #lista-opciones")


def test_el_titulo_arranca_a_ras_de_la_portada_y_sin_pie():
    assert "margin-top: 0" in regla(".issue-titulos h1")
    assert "issue-portada-pie" not in FICHA and "issue-portada-pie" not in CSS


def test_en_el_movil_la_portada_queda_junto_al_titulo():
    inicio = CSS.index("@media (max-width: 480px) {\n  .ficha-serie-meta > div")
    bloque = CSS[inicio:CSS.index("\n}", inicio)]
    assert 'grid-template-areas: "portada titulos" "acciones acciones"' in bloque


def test_cada_etiqueta_de_tu_lectura_va_con_su_control():
    nota = LECTURA.split('<div class="lectura-campo-nota">', 1)[1].split("</div>", 1)[0]
    assert "nota_corta" in nota and "<textarea" in nota and "max_nota" in nota
    assert 'aria-describedby="nota-max-' in nota
    assert "display: grid" in regla(".lectura-bloque form")


def test_la_garantia_va_junto_al_boton_de_guardar():
    formulario = LECTURA.split("<form", 1)[1].split("</form>", 1)[0]
    boton = formulario.index("guardar_mi_lectura")
    assert boton < formulario.index("textos_lectura.garantia")


def test_solo_la_garantia_va_en_caja_amarilla():
    """La ayuda es texto secundario; el amarillo, solo para la garantía (PO, 2026-11-20)."""
    assert '<p class="muted">{{ textos_lectura.ayuda }}</p>' in LECTURA
    assert LECTURA.count('class="caption"') == 1
    assert '<p class="caption">{{ textos_lectura.garantia }}</p>' in LECTURA
