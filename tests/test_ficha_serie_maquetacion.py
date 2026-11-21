"""Regresión: maquetación de la ficha de serie (revisión del 2026-11-21).

Ficha de benchmark y reglas del sistema de diseño en
`docs/design/benchmark-ficha-serie-maquetacion.md`.

1. Las acciones iban en cinco alturas (tomo único, favorita, editar y añadir, retirar, aviso legal):
   ahora una fila con la principal primero; lo poco frecuente, plegado al final de la cabecera.
2. El título bajaba 19 px respecto a la portada; en el móvil la portada iba sola arriba.
3. «Completar datos», una página aparte, estaba en la barra de secciones; la barra no seguía el
   orden de la página.
4. Ninguna sección era una viñeta (`.card`) y los huecos entre ellas iban de 18 a 38 px.
5. «Archivos por número» desplegaba todos los números (11.630 px de 14.632 en una serie de 100).
6. Tres didascalias eran ayuda; la de autores salía sin autores; un chip de seis palabras; «Quitar»
   de 36 px; el motivo de «no se puede calcular» empezaba en minúscula.
7. Las acciones de Biblioteca y de la ficha de número eran `ghost` repintados: el sistema de diseño
   define `ghost` como subrayado y sin borde; el botón con borde y sombra es el neutro (`.btn.sm`).
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"


def plantilla(nombre: str) -> str:
    return (PLANTILLAS / nombre).read_text(encoding="utf-8")


FICHA = plantilla("series_detail.html")


def regla(selector: str) -> str:
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert m, f"no existe la regla {selector} en web.css"
    return m.group(1)


def cabecera() -> str:
    return FICHA.split('<div class="series-header">', 1)[1].split('<nav class="ficha-nav"', 1)[0]


def acciones() -> str:
    return cabecera().split('<div class="series-acciones">', 1)[1].split("</div>", 1)[0]


def test_un_solo_enlace_de_vuelta():
    # Las dos ramas (`volver` o «← Biblioteca») en una sola línea: nunca se pintan los dos.
    assert FICHA.count('class="back-link"') == 2
    assert len([linea for linea in FICHA.splitlines() if 'class="back-link"' in linea]) == 1


def test_las_acciones_van_en_una_fila_y_la_principal_primero():
    fila = acciones()
    piezas = ("Añadir números del disco", "Editar la ficha", "Completar datos",
              "_favorito_boton.html")
    orden = [fila.index(t) for t in piezas]
    assert orden == sorted(orden)
    assert fila.count("primary") == 1 and "ghost" not in fila


def test_lo_poco_frecuente_va_plegado_despues_de_las_acciones():
    resto = cabecera().split('<div class="series-poco-frecuente">', 1)[1]
    for pieza in ("_obra_unica_serie.html", 'class="series-retirar"', 'class="series-fuentes"'):
        assert pieza in resto, pieza
    assert cabecera().index('class="series-acciones"') < cabecera().index("series-poco-frecuente")


def test_el_titulo_arranca_a_ras_y_en_el_movil_la_portada_va_junto_al_titulo():
    assert "margin-top: 0" in regla(".series-titulos h1")
    assert 'grid-template-areas: "portada titulos" "portada acciones"' in regla(".series-header")
    inicio = CSS.index("  .portada.series-cover { width: 88px; }")
    movil = CSS[inicio:CSS.index("\n}", inicio)]
    assert 'grid-template-areas: "portada titulos" "acciones acciones"' in movil


def test_la_barra_sigue_el_orden_de_la_pagina_y_no_lleva_completar_datos():
    nav = FICHA.split('<nav class="ficha-nav"', 1)[1].split("</nav>", 1)[0]
    assert "/datos" not in nav
    anclas = re.findall(r'href="#([\w-]+)"', nav)
    cuerpo = FICHA.split("</nav>", 1)[1]
    parciales = {"politica-serie": "_politica_serie.html",
                 "seguimiento-serie": "_seguimiento_serie.html"}

    def posicion(ancla: str) -> int:
        if ancla in parciales:
            return cuerpo.index(f'include "{parciales[ancla]}"')
        return cuerpo.index(f'id="{ancla}"')

    posiciones = [posicion(a) for a in anclas]
    assert posiciones == sorted(posiciones), anclas


def test_cada_seccion_es_una_vineta_con_el_mismo_hueco():
    for nombre in ("_politica_serie.html", "_seguimiento_serie.html", "_etiquetas_serie.html",
                   "_colecciones_serie.html", "_sagas_serie.html", "_nota_serie.html"):
        assert "card ficha-bloque" in plantilla(nombre), nombre
    for ancla in ("numeros-serie", "datos-serie", "coleccion-serie", "archivos-por-numero"):
        etiqueta = re.search(rf'<section[^>]*id="{ancla}"[^>]*>', FICHA) or re.search(
            rf'<section[^>]*class="[^"]*"[^>]*id="{ancla}"[^>]*>', FICHA)
        assert etiqueta and "card ficha-bloque" in etiqueta.group(0), ancla
    assert "margin: 0 0 var(--space-4)" in regla(".ficha-bloque")


def test_los_marcadores_perezosos_no_pintan_una_vineta_vacia():
    for ancla in ("sagas-serie", "etiquetas-serie", "colecciones-serie"):
        etiqueta = re.search(rf'<section id="{ancla}"[^>]*>', FICHA).group(0)
        assert "hx-get" in etiqueta and "card" not in etiqueta, ancla


def test_los_archivos_se_pliegan_despues_de_los_primeros():
    bloque = FICHA.split('id="archivos-por-numero"', 1)[1].split("</section>", 1)[0]
    assert "{% if loop.index0 == limite %}" in bloque
    assert '<details class="ficha-mas">' in bloque
    assert "{% if restantes_archivos > 0 %}</details>{% endif %}" in bloque


def test_las_ayudas_no_van_en_caja_amarilla_y_la_procedencia_solo_con_datos():
    assert '<p class="muted">Una obra autoconclusiva' in plantilla("_obra_unica_serie.html")
    assert '<p class="muted politica-futuros"' in plantilla("_politica_serie.html")
    leyenda = FICHA.split("{% if hay_manual or hay_bloqueado %}", 1)[1][:40]
    assert '<p class="muted">' in leyenda
    autores = FICHA.split("{{ textos_ficha.autores }}", 1)[1]
    condicion = autores.index("{% if ficha and ficha.autores %}")
    assert condicion < autores.index("Los que más números firman")


def test_chips_de_tres_palabras_como_mucho():
    for nombre in ("series_detail.html", "issue_detail.html", "_retirada_panel.html"):
        texto = plantilla(nombre)
        assert '"Quizá no esté en el disco") }}' not in texto, nombre
        assert ('{{ ui.chip("amber", "Por confirmar") }} '
                '<span class="muted">Quizá no esté en el disco</span>') in texto


def test_quitar_una_etiqueta_mide_40_px():
    bloque = regla(".etiqueta-x")
    assert "min-width: 40px; min-height: 40px" in bloque


def test_el_motivo_sin_calcular_es_una_frase():
    for texto in (FICHA, plantilla("_politica_serie.html")):
        assert "m[:1]|upper ~ m[1:]" in texto


def test_las_acciones_son_botones_neutros_y_no_ghost_repintados():
    assert ".issue-acciones .btn.ghost" not in CSS
    assert ".biblioteca-acciones .biblioteca-accion {" not in CSS
    numero = plantilla("issue_detail.html")
    fila = numero.split('<div class="issue-acciones">', 1)[1].split("</details>", 1)[0]
    assert "ghost" not in fila and fila.count('class="btn sm"') == 4
    assert "btn sm favorito-btn-ficha" in plantilla("_favorito_boton.html")


def test_los_botones_del_titulo_del_numero_no_heredan_la_rotulacion():
    bloque = regla(".archivos-numero-titulo .btn")
    assert "font-family: var(--font-body)" in bloque and "text-transform: none" in bloque
