"""Portada que falta: marcador DEBAJO y portada ENCIMA, sin JavaScript (opción A de la propuesta).

Por qué el marcador va debajo y no «en lugar de» la imagen: la caché de portadas se llena al PEDIR
`/ui/series/{id}/portada` (se extrae del CBZ o se descarga entonces), así que el servidor no sabe en el
render si habrá portada, y decidirlo obligaría a ejecutar la cascada por tarjeta (CLAUDE.md §4).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest

from zascarr.web.portada_marca import (
    COLORES,
    INICIAL_DE_RESPALDO,
    color_de_portada,
    inicial_de_portada,
    marca_de_portada,
)
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1] / "src" / "zascarr"
CSS = (RAIZ / "static" / "web.css").read_text(encoding="utf-8")
CSS_SIN_COMENTARIOS = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)


class TestInicial:
    @pytest.mark.parametrize("titulo,esperada", [
        ("Mortadelo y Filemón", "M"), ("¡Zas! Tebeo", "Z"), ("1984", "1"), ("Ásterix", "Á"),
        ("  «ñandú»", "Ñ"), ("...Y entonces", "Y"), ("el capitán", "E"),
    ])
    def test_toma_el_primer_caracter_alfanumerico_en_mayuscula(self, titulo, esperada):
        assert inicial_de_portada(titulo) == esperada

    @pytest.mark.parametrize("titulo", ["", None, "¡¡¡", "···", "   "])
    def test_sin_ningun_alfanumerico_hay_respaldo(self, titulo):
        assert inicial_de_portada(titulo) == INICIAL_DE_RESPALDO

    def test_una_a_con_tilde_descompuesta_sale_entera(self):
        assert inicial_de_portada("Ángel") == "Á"                      # NFC: la Á, no una A suelta


class TestColor:
    def test_con_identificador_es_id_modulo_tres(self):
        for n in range(6):
            assert color_de_portada(UUID(int=n)) == COLORES[n % 3]

    def test_un_identificador_en_texto_vale_igual_que_el_uuid(self):
        u = UUID("12345678-1234-5678-1234-567812345678")
        assert color_de_portada(str(u)) == color_de_portada(u) == COLORES[u.int % 3]

    def test_sin_identificador_es_estable_y_no_distingue_mayusculas_ni_tildes(self):
        assert (color_de_portada(None, "Ásterix") == color_de_portada(None, "asterix")
                == color_de_portada(None, "ASTERIX"))

    def test_el_color_sin_identificador_es_un_valor_fijado_no_hash_de_python(self):
        """Valores fijados a mano: si alguien lo cambia a `hash()` (distinto por proceso) esto se rompe."""
        assert [color_de_portada(None, t) for t in ("Batman", "Flash", "Ásterix", "Zipi y Zape")] == \
            ["m", "y", "m", "y"]

    def test_es_el_mismo_en_otro_proceso_con_otra_semilla_de_hash(self):
        codigo = ("from zascarr.web.portada_marca import color_de_portada as c;"
                  "print(c(None,'Batman'), c(None,'Flash'), c(None,'Ásterix'))")
        salidas = {subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True,
                                  env={"PYTHONHASHSEED": semilla, "PATH": "", "PYTHONPATH": str(RAIZ.parent)},
                                  check=True).stdout.strip()
                   for semilla in ("1", "2", "random")}
        assert len(salidas) == 1

    def test_los_tres_colores_aparecen(self):
        titulos = [f"Serie {n}" for n in range(60)]
        assert {color_de_portada(None, t) for t in titulos} == set(COLORES)

    def test_marca_junta_color_e_inicial(self):
        m = marca_de_portada("Ásterix", UUID(int=4))
        assert (m.color, m.inicial) == (COLORES[4 % 3], "Á")


@pytest.fixture(scope="module")
def ui():
    return crear_templates().env


def _pintar(env, expr: str, **ctx) -> str:
    return env.from_string("{{ " + expr + " }}").render(**ctx)


class TestMacro:
    def test_el_marcador_va_antes_de_la_imagen_y_es_decorativo(self, ui):
        h = _pintar(ui, 'ui.portada("Ásterix", id, "/ui/series/x/portada")', id=UUID(int=1))
        assert h.index('class="portada-marca"') < h.index("<img")
        assert 'class="portada-marca" aria-hidden="true">Á</span>' in h
        assert '<img src="/ui/series/x/portada" alt="">' in h

    def test_sin_src_no_hay_imagen_que_pueda_fallar(self, ui):
        h = _pintar(ui, 'ui.portada("Flash")')
        assert "<img" not in h and 'class="portada portada-' in h

    def test_la_clase_del_contexto_se_anade_al_contenedor_no_a_la_imagen(self, ui):
        h = _pintar(ui, 'ui.portada("Flash", none, "/x", "series-cover")')
        assert re.search(r'^<span class="portada portada-[cmy] series-cover">', h)
        assert "<img" in h and "series-cover" not in h[h.index("<img"):]

    def test_el_titulo_se_escapa(self, ui):
        h = _pintar(ui, "ui.portada(t)", t="<b>x</b>")
        assert "<b>" not in h


class TestPlantillas:
    def test_ninguna_plantilla_lleva_onerror(self):
        """Regresión: el último JS en atributo sostenía el estado visual de la portada que falta."""
        con = [str(p.relative_to(RAIZ)) for p in (RAIZ / "web" / "templates").rglob("*.html")
               if "onerror" in p.read_text(encoding="utf-8").lower()]
        assert con == []

    def test_ninguna_plantilla_pinta_la_clase_cover_missing(self):
        con = [p.name for p in (RAIZ / "web" / "templates").rglob("*.html")
               if "cover-missing" in p.read_text(encoding="utf-8")]
        assert con == []

    @pytest.mark.parametrize("plantilla", ["_rejilla_biblioteca.html", "dashboard.html", "series_detail.html"])
    def test_las_portadas_de_serie_usan_la_macro_y_alt_vacio(self, plantilla):
        t = (RAIZ / "web" / "templates" / plantilla).read_text(encoding="utf-8")
        assert "ui.portada(" in t and "/portada" in t and "<img" not in t.replace("ui.portada", "")


def _reglas():
    return [(" ".join(s.split()), d) for s, d in re.findall(r"([^{}@]+)\{([^{}]*)\}", CSS_SIN_COMENTARIOS)]


class TestCss:
    def test_la_imagen_no_pinta_fondo_borde_ni_sombra_propios(self):
        """Condición del diseño: en Chrome una imagen rota con tamaño fijado por CSS sigue pintando su
        fondo y taparía el marcador. Ninguna regla de `img` dentro de una portada puede dar fondo/borde."""
        propias = [(s, d) for s, d in _reglas() if re.search(r"\.portada\s+img\b", s)]
        assert propias
        for s, d in propias:
            assert re.search(r"background:\s*none", d) and re.search(r"border:\s*0", d), s
            assert "box-shadow: none" in d, s
        for s, _d in _reglas():
            if re.search(r"(series-card|library-card|discovery-card)\s+(img|\.cover)\b", s):
                pytest.fail(f"regla de imagen por contexto que reintroduce marco en la <img>: {s}")

    def test_la_imagen_no_fija_el_alto_para_que_una_rota_no_pinte_su_icono(self):
        """Hallazgo medido en Chromium: una `<img>` rota con ancho Y alto por CSS pinta el icono de
        imagen rota y su filete aunque lleve alt="". Sin `height` (solo min/max-height) se colapsa."""
        d = next(d for s, d in _reglas() if re.search(r"\.portada\s+img\b", s))
        assert not re.search(r"(?<![-\w])height\s*:", d) and "inset" not in d, d
        assert "min-height: 100%" in d and "max-height: 100%" in d and "object-fit: cover" in d

    def test_el_marco_va_en_el_contenedor_de_cada_contexto(self):
        contextos = (".library-card .portada", ".series-card .portada", ".discovery-card .portada",
                     ".portada.series-cover")
        for contexto in contextos:
            assert any(s == contexto and "border" in d for s, d in _reglas()), contexto

    def test_el_ancho_de_la_ficha_gana_al_de_la_portada_generica(self):
        """Hallazgo medido en el navegador: `.series-cover` (140 px) iba ANTES de `.portada` (100 %) con la
        misma especificidad y la portada de la ficha salía a todo el ancho. Por eso es `.portada.series-cover`."""
        assert any(s == ".portada.series-cover" and "width: 140px" in d for s, d in _reglas())
        assert not any(s == ".series-cover" for s, _d in _reglas())

    def test_el_marcador_aguanta_sin_cqw(self):
        d = next(d for s, d in _reglas() if s == ".portada-marca")
        assert d.index("font-size: 2.6rem") < d.index("46cqw")                       # respaldo antes de la unidad nueva

    def test_con_contraste_alto_el_marcador_es_papel_liso(self):
        bloque = re.search(r"@media \(prefers-contrast: more\), \(forced-colors: active\)\s*\{(.*?)\n\}",
                           CSS_SIN_COMENTARIOS, re.S).group(1)
        plano = " ".join(bloque.split())
        assert ".portada-c, .portada-m, .portada-y { background: var(--paper-2); color: var(--ink); }" in plano


class TestContrasteDeLaInicial:
    """La inicial es texto grande y decorativo: le basta 3:1. Se comprueba aquí en las tres tintas y los
    dos temas, porque la excepción de test_web_css_contraste.py solo la cubre a ella."""

    @pytest.mark.parametrize("tema", ["claro", "oscuro"])
    @pytest.mark.parametrize("tinta", ["cyan", "magenta", "yellow"])
    def test_la_inicial_se_lee_sobre_cada_tinta(self, tema, tinta):
        from tests.test_web_css_contraste import _temas, contraste, resolver
        t = _temas()[tema]
        assert contraste(resolver("var(--on-yellow)", t), resolver(f"var(--{tinta})", t)) >= 3.0

    def test_cada_tinta_pone_su_color_y_su_fondo_solido_en_la_misma_regla(self):
        """Para que la prueba de contraste de la hoja mida el par real y no el fondo de contexto."""
        for clase, tinta in (("c", "cyan"), ("m", "magenta"), ("y", "yellow")):
            d = next(d for s, d in _reglas() if s == f".portada-{clase}")
            assert f"background-color: var(--{tinta})" in d and "color: var(--on-yellow)" in d
