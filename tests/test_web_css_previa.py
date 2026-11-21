"""UATP-05: la previa es hoverable, solo hay una y la fija no se abre por hover.

BL-INF4 la mostró con hover/foco; UATP-05 (#1143) la hace descartable y la convierte en zona
de puntero (WCAG 1.4.13) sin JS. Estas pruebas fijan las reglas CSS del contrato.
"""
from __future__ import annotations

from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "src/zascarr/static/web.css").read_text()
CSS_PLANO = " ".join(CSS.split())


def _regla(selector: str) -> str:
    """Cuerpo de la primera regla cuyo selector exacto es `selector` (sin normalizar)."""
    marca = "\n" + selector + " {"
    assert marca in CSS, f"falta la regla {selector}"
    cuerpo = CSS.split(marca, 1)[1].split("}", 1)[0]
    return " ".join(cuerpo.split())


def test_la_previa_se_muestra_solo_con_hover_o_foco_del_chip():
    # La anclada se abre con el puntero; la fija, solo con foco o con su botón (D-4).
    assert ".chip-previa:not(.chip-previa-lista):hover > .previa-numero:not(:empty)" in CSS
    assert ".chip-previa:focus-within > .previa-numero:not(:empty)" in CSS
    # Por defecto, oculta: si no, se acumularían las de los chips ya visitados.
    assert "display: none;" in _regla(".previa-numero")


def test_la_fija_no_se_abre_al_pasar_el_raton():
    assert ".chip-previa:hover > .previa-numero" not in CSS_PLANO


def test_la_tarjeta_es_zona_de_puntero_y_no_deja_pasar_el_clic():
    assert "pointer-events: none" not in _regla(".previa-numero")
    assert "pointer-events: none" not in _regla(".chip-previa-lista > .previa-numero")


def test_puente_de_8px_solo_en_la_anclada():
    puente = _regla(".chip-previa:not(.chip-previa-lista) > .previa-numero::after")
    assert "position: absolute" in puente
    assert "top: -8px; height: 8px;" in puente


def test_el_recorte_pasa_a_la_tarjeta_interior_para_que_se_vea_la_flecha():
    # El contenedor dibuja la flecha (::before) y el puente (::after): no puede recortarlos.
    assert "overflow: hidden" not in _regla(".previa-numero")
    assert "overflow: hidden" in _regla(".previa-card")
    assert ".previa-numero::before" in CSS


def test_una_sola_previa_con_prioridad_del_foco():
    selector = ("body:has(.chip-previa:focus-within > .previa-numero:not(:empty)) "
                ".chip-previa:hover:not(:focus-within) > .previa-numero:not(:empty)")
    assert selector + " { display: none; }" in CSS_PLANO


def test_el_boton_ver_portada_se_ve_tambien_con_puntero_fino():
    # La fija ya no se abre con hover: el disparador explícito no puede quedar solo en táctil.
    assert (".chip-previa-boton { display: inline-flex; align-items: center; "
            "min-height: 44px; }") in CSS_PLANO
    assert "@media (hover: none), (pointer: coarse) { .chip-previa-boton" not in CSS_PLANO


def test_sigue_oculta_en_movil_y_puntero_grueso():
    regla = "@media (max-width: 860px), (pointer: coarse) { .previa-numero { display: none; } }"
    assert regla in CSS

    # La fija conserva su vuelta en móvil al recibir foco (regla existente).
    assert ".chip-previa-lista:focus-within > .previa-numero:not(:empty)" in CSS


def test_pie_de_la_previa_a_14px_y_cifras_tabulares():
    pie = _regla(".previa-pie")
    assert "font-size: var(--text-secundario)" in pie
    assert "font-variant-numeric: tabular-nums" in _regla(".previa-pie strong")
