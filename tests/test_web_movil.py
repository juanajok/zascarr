# ruff: noqa: E501
"""U16 (#203): contratos del móvil que se pueden comprobar SIN navegador. La medida real (desborde, tamaño de fuente y alto
de los controles, por pantalla y por ancho) está en `docs/design/ui-u16/` y se repite con `medir_u16.py` en Chrome; estas pruebas solo
impiden que los tres defectos medidos vuelvan por una edición del CSS o de una plantilla."""
from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1] / "src" / "zascarr"
CSS = (RAIZ / "static" / "web.css").read_text(encoding="utf-8")
SIN_COMENTARIOS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
PLANTILLAS = sorted((RAIZ / "web" / "templates").glob("*.html"))


def _bloque_movil() -> str:
    m = re.search(r"@media \(max-width: 860px\), \(pointer: coarse\) \{(.*?)\n\}\n", CSS, re.S)
    assert m, "falta el bloque táctil de U16 al final de web.css"
    return m.group(1)


class TestBarraInferior:
    def test_las_columnas_nunca_superan_el_ancho(self):
        """Regresión del desborde medido (ficha de serie +53 px y aviso legal +49 px a 360 px): con `minmax(max-content, 1fr)` la barra
        fija se hacía más ancha que la pantalla en cuanto una etiqueta o una tabla ensanchaba la página."""
        assert "minmax(max-content" not in SIN_COMENTARIOS
        assert "grid-template-columns: repeat(5, minmax(0, 1fr))" in SIN_COMENTARIOS

    def test_la_etiqueta_se_reduce_con_el_ancho(self):
        assert re.search(r"\.nav-enlace \{[^}]*font-size: clamp\(", CSS, re.S)


class TestZoomYObjetivos:
    def test_los_campos_miden_16px_o_mas_y_44_de_alto(self):
        """Safari en iOS amplía la página al enfocar un campo de menos de 16 px; los campos medían 14,4 px (14 en Ajustes)."""
        b = _bloque_movil()
        campos = re.search(r"input:not.*?\{(.*?)\}", b, re.S).group(1)
        assert "font-size: 1rem" in campos and "min-height: 44px" in campos
        assert "select:not" in b and "textarea:not" in b

    def test_botones_y_resumenes_miden_44px(self):
        b = _bloque_movil()
        reglas = re.search(r"button:not.*?\{(.*?)\}", b, re.S)
        assert reglas and "min-height: 44px" in reglas.group(1)
        assert "summary:not" in b and ".btn:not" in b

    def test_las_casillas_siguen_en_24px(self):
        assert re.search(r'input\[type="checkbox"\], input\[type="radio"\] \{\s*width: 24px; height: 24px', CSS)

    def test_el_bloque_no_usa_important(self):
        assert "!important" not in _bloque_movil()


class TestSelectorDeLaFicha:
    def test_el_selector_de_politica_no_supera_su_contenedor(self):
        """El ancho de un `<select>` es el de su opción más larga: sin tope desbordaba la ficha de serie en el móvil."""
        regla = re.search(r"\.politica-form select \{(.*?)\}", CSS, re.S).group(1)
        assert "max-width: 100%" in regla and "min-width: 0" in regla

    def test_las_tablas_del_aviso_legal_parten_las_palabras_largas(self):
        assert re.search(r"\.legal-full th, \.legal-full td \{ overflow-wrap: anywhere; \}", CSS)


class TestEnlacesDeVolver:
    def test_los_enlaces_de_volver_usan_la_clase_de_objetivo_suficiente(self):
        """Un enlace «← Volver…» suelto medía 22 px (por debajo del mínimo de 24): todos llevan `.back-link`."""
        sin_clase = []
        for p in PLANTILLAS:
            for a in re.findall(r"<a ([^>]*)>←\s*(?:Volver|Biblioteca)", p.read_text(encoding="utf-8")):
                if "back-link" not in a and "btn" not in a and "pend-" not in a:
                    sin_clase.append(p.name)
        assert sin_clase == []
