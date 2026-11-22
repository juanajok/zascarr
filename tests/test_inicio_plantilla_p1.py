"""El Inicio sigue la plantilla P1 «Losa y satélites» (docs/design/plantillas-de-pagina.md).

Se comprueba lo que una plantilla puede garantizar sin navegador: el orden del HTML (que es el de
lectura), que cada viñeta usa un reparto del vocabulario cerrado, que el único botón principal va
en la losa y que la losa es la única viñeta con sombra. El reflujo y el alto de las filas se
verificaron en el navegador (1280, 375 y 320 px) al hacer el prototipo.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from uuid import uuid4

from tests.test_web_dashboard import pagina, vista
from zascarr.services.inicio import ContinuarLeyendo
from zascarr.services.library_adopter import EstadoAdopcion
from zascarr.services.resumen import ULTIMAS_SERIES

CSS = Path(__file__).resolve().parents[1] / "src" / "zascarr" / "static" / "web.css"
SPANS = {"inicio-losa", "inicio-cifras", "inicio-par", "inicio-ancha"}


class _Pagina(HTMLParser):
    """Hijos directos de `.inicio-pagina` (sus clases) y en cuál cae cada botón principal."""

    def __init__(self):
        super().__init__()
        self._pila: list[str] = []
        self._raiz: int | None = None
        self.vinetas: list[set[str]] = []
        self.primarios: list[set[str]] = []

    def handle_starttag(self, tag, attrs):
        clases = set((dict(attrs).get("class") or "").split())
        if self._raiz is not None and len(self._pila) == self._raiz + 1:
            self.vinetas.append(clases)
        if tag == "a" and "primary" in clases:
            self.primarios.append(self.vinetas[-1] if self._en_pagina() else set())
        if tag in {"input", "img", "br", "meta", "link"}:
            return
        self._pila.append(tag)
        if "inicio-pagina" in clases:
            self._raiz = len(self._pila) - 1

    def handle_endtag(self, tag):
        if tag in {"input", "img", "br", "meta", "link"}:
            return
        self._pila.pop()
        if self._raiz is not None and len(self._pila) == self._raiz:
            self._raiz = None

    def _en_pagina(self) -> bool:
        return self._raiz is not None and len(self._pila) > self._raiz + 1


def _analiza(html: str) -> _Pagina:
    p = _Pagina()
    p.feed(html)
    return p


LECTURA = ContinuarLeyendo(series_id=str(uuid4()), series_title="Thorgal", issue_id=str(uuid4()),
                           issue_number="3", issue_title=None, current_page=5, page_count=20)

ESTADOS = {
    "instalación nueva": vista(),
    "pasos a medias": vista(adopcion=EstadoAdopcion.PENDIENTE),
    "lo básico hecho, leyendo": vista(adopcion=EstadoAdopcion.HECHA, registrados=10, series=3,
                                      continuar=LECTURA),
    "con cifras, sin lectura": vista(adopcion=EstadoAdopcion.HECHA, registrados=10, series=3),
}


def _bloque(v) -> list[str]:
    """Las viñetas por su función, en el orden del HTML."""
    orden = []
    for clases in _analiza(pagina(v)).vinetas:
        for nombre in ("primeros-pasos", "inicio-cifras", "continuar-leyendo", "latest-updates",
                       "discover"):
            if nombre in clases:
                orden.append(nombre)
    return orden


def test_el_orden_del_html_es_el_de_lectura():
    assert _bloque(ESTADOS["lo básico hecho, leyendo"]) == [
        "primeros-pasos", "inicio-cifras", "continuar-leyendo", "latest-updates", "discover"]
    assert _bloque(ESTADOS["instalación nueva"]) == ["primeros-pasos", "latest-updates", "discover"]


def test_cada_vineta_usa_un_reparto_del_catalogo_y_los_pares_van_de_dos_en_dos():
    for nombre, v in ESTADOS.items():
        vinetas = _analiza(pagina(v)).vinetas
        assert vinetas, nombre
        for clases in vinetas:
            # La losa sin cifras al lado lleva además `inicio-ancha`, que manda sobre su span de 8.
            manda = {"inicio-losa"} if "inicio-ancha" in clases else set()
            assert len(clases & SPANS - manda) == 1, (nombre, clases)
        pares = sum("inicio-par" in c for c in vinetas)
        assert pares in (0, 2), nombre
        # Losa 8 + cifras 4: o van las dos, o la losa ocupa todo el ancho.
        losa = next(c for c in vinetas if "primeros-pasos" in c)
        con_cifras = any("inicio-cifras" in c for c in vinetas)
        assert ("inicio-ancha" in losa) != con_cifras, nombre


def test_sin_cifras_la_losa_ocupa_todo_el_ancho_y_sin_lectura_las_ultimas_tambien():
    vinetas = _analiza(pagina(ESTADOS["instalación nueva"])).vinetas
    losa = next(c for c in vinetas if "primeros-pasos" in c)
    assert {"inicio-losa", "inicio-ancha"} <= losa
    ultimas = next(c for c in vinetas if "latest-updates" in c)
    assert "inicio-ancha" in ultimas and "inicio-par" not in ultimas


def test_el_unico_boton_principal_va_en_la_losa():
    for nombre, v in ESTADOS.items():
        primarios = _analiza(pagina(v)).primarios
        assert len(primarios) <= 1, nombre
        assert all("inicio-losa" in c for c in primarios), nombre


def _bloque_css() -> str:
    css = CSS.read_text(encoding="utf-8")
    ini = css.index("15c. INICIO")
    return css[ini:css.index("/* ── 16.", ini)]


def test_la_losa_es_la_unica_sombra_de_la_pagina():
    bloque = _bloque_css()
    sombras = re.findall(r"([^{}]+)\{[^}]*box-shadow:\s*([^;]+);", bloque)
    con_sombra = [sel.strip().split("\n")[-1] for sel, valor in sombras if valor.strip() != "none"]
    assert con_sombra == [".inicio-losa"]
    css = CSS.read_text(encoding="utf-8")
    continuar = re.search(r"\.continuar-card \{([^}]*)\}", css).group(1)
    assert "box-shadow" not in continuar


def test_la_reticula_es_de_12_con_el_medianil_de_las_vinetas_y_sin_reordenar():
    bloque = _bloque_css()
    assert "grid-template-columns: repeat(12, minmax(0, 1fr));" in bloque
    assert "gap: var(--space-3);" in bloque
    sin_comentarios = re.sub(r"/\*.*?\*/", "", bloque, flags=re.S)
    assert not re.search(r"(?<![-\w])order:", sin_comentarios)          # «border:» no cuenta
    assert "grid-template-areas" not in sin_comentarios
    spans = set(re.findall(r"grid-column: span (\d+);", bloque))
    assert spans <= {"4", "6", "8"}


def test_ultimas_actualizaciones_cabe_en_una_fila_de_seis():
    assert ULTIMAS_SERIES == 6
