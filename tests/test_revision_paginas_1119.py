"""Revisión de páginas del 2026-11-19: regresiones de lo corregido contra el sistema de diseño.

1. Deseados: el aviso «buscando» (`.htmx-indicator`) se oculta con opacity/visibility, que
   conservan su sitio; fuera de una petición no debe ocupar alto en la fila.
2. Biblioteca: las píldoras de filtro van fuera del enlace de la tarjeta; el marco está en el
   envoltorio para que tarjeta y píldoras sean una sola viñeta, y la rejilla intermedia da dos
   columnas en el móvil.
3. Jerarquía de texto: `.caption` es una caja de lectura (didascalia), no la letra de un contador
   o una fecha; `.titulo-frase` es para títulos de más de 3 palabras; `.rotulo` (girado, con
   sombra) no es la etiqueta de un control; un solo `.primary` por pantalla.
4. Glosario (§14): el Inicio habla de la «tebeoteca», no de la «colección».
5. Novedades: la portada repite el enlace del título; fuera del tabulado y del lector de pantalla.
"""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CSS = (RAIZ / "src" / "zascarr" / "static" / "web.css").read_text(encoding="utf-8")
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"


def plantilla(nombre: str) -> str:
    return (PLANTILLAS / nombre).read_text(encoding="utf-8")


def regla(selector: str) -> str:
    """Cuerpo de la primera regla cuyo selector exacto empieza por `selector`."""
    m = re.search(rf"(?m)^\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", CSS)
    assert m, f"no existe la regla {selector} en web.css"
    return m.group(1)


class TestIndicadorDeDeseados:
    def test_el_indicador_inactivo_no_reserva_alto_en_la_fila(self):
        assert "display: none" in regla(
            ".wishlist-buscando.htmx-indicator:not(.htmx-request),\n"
            "#buscando-lote.htmx-indicator:not(.htmx-request)")


class TestTarjetaDeBiblioteca:
    def test_el_marco_esta_en_el_envoltorio_y_no_en_la_tarjeta(self):
        assert "border:" in regla(".library-grid .library-card-wrap")
        assert "border: 0" in regla(".library-grid .library-card-wrap > .library-card")

    def test_las_pildoras_se_apoyan_al_pie_de_la_vineta(self):
        assert "margin-top: auto" in regla(".library-grid .library-card-wrap > .library-card-chips")

    def test_la_rejilla_intermedia_da_dos_columnas_en_el_movil(self):
        m = re.search(
            r"@media \(max-width: 480px\) \{\s*\.library-grid-intermedia \{([^}]*)\}", CSS)
        assert m and "repeat(2," in m.group(1)

    def test_las_pildoras_dicen_que_filtran(self):
        texto = plantilla("_rejilla_biblioteca.html")
        assert 'aria-label="Filtrar por año:' in texto
        assert 'aria-label="Filtrar por tradición:' in texto


class TestJerarquiaDeTexto:
    def test_contadores_y_fechas_no_van_en_caja_de_lectura(self):
        casos = {
            "arcos.html": "{{ pagina.total }}",
            "arco.html": "{{ arco.filas | length }}",
            "novedades.html": "{{ semana.total }}",
            "estado.html": "{{ cobertura.texto_fecha }}",
            "mejoras.html": "Tu copia:",
            "issue_detail.html": "{{ textos.portada_numero }}",
        }
        for nombre, marca in casos.items():
            for linea in plantilla(nombre).splitlines():
                if marca in linea:
                    assert 'class="caption"' not in linea, f"{nombre}: {linea.strip()}"

    def test_titulos_de_una_palabra_no_llevan_titulo_frase(self):
        for nombre in ("_sagas_serie.html", "_colecciones_serie.html", "_nota_serie.html",
                       "series_detail.html", "issue_detail.html"):
            for h2 in re.findall(r"<h2[^>]*>[^<]*</h2>", plantilla(nombre)):
                visible = re.sub(r"<[^>]+>", "", h2)
                if "{{" not in visible and len(visible.split()) <= 3:
                    assert "titulo-frase" not in h2, f"{nombre}: {h2}"

    def test_la_etiqueta_por_pagina_no_es_un_rotulo(self):
        assert '<span class="rotulo">Por página:</span>' not in plantilla("pendientes.html")

    def test_guardar_la_lectura_no_compite_con_leer(self):
        assert "btn primary" not in plantilla("_lectura_control.html")


class TestGlosario:
    def test_el_inicio_habla_de_la_tebeoteca(self):
        texto = plantilla("dashboard.html")
        assert "Tu tebeoteca ahora" in texto
        assert "Tu colección ahora" not in texto


class TestNovedades:
    def test_la_portada_no_duplica_el_enlace_del_titulo(self):
        texto = plantilla("novedades.html")
        assert 'tabindex="-1" aria-hidden="true"' in texto
        assert 'aria-label="Abrir la serie {{ n.serie }}"' not in texto
