"""Regresión: lo que ZascArr iguala de los sistemas de diseño de referencia (2026-11-22).

Ficha: `docs/design/benchmark-designsystems-surf.md` (ideas A1–A4, B1–B2, C1, D1, D3, F3 y G2); las
reglas, en `docs/design/sistema-de-diseno-zascarr.md`. B1 lo cubre `test_web_library`; los envíos
con errores contra Postgres, `test_estructura_pantallas_pg`.
"""
from __future__ import annotations

import re
from pathlib import Path

from zascarr.services.arcos import _titulo
from zascarr.web.routes import crear_templates

RAIZ = Path(__file__).resolve().parents[1]
PLANTILLAS = RAIZ / "src" / "zascarr" / "web" / "templates"
WEB = RAIZ / "src" / "zascarr" / "web"


def _render(fuente: str, **ctx) -> str:
    return crear_templates().env.from_string(fuente).render(**ctx)


def _visible(texto: str) -> str:
    """El texto de una plantilla sin comentarios de Jinja ni de HTML (lo que puede verse)."""
    texto = re.sub(r"\{#.*?#\}", " ", texto, flags=re.S)
    return re.sub(r"<!--.*?-->", " ", texto, flags=re.S)


FORMULARIO = ('{% set orden_campos = ["a", "b"] %}{{ ui.resumen_errores(errores, orden_campos) }}'
              '<input name="a"{{ ui.invalido(errores, "a", orden_campos) }}>'
              '<input name="b"{{ ui.invalido(errores, "b", orden_campos, "ayuda-b") }}>')


def test_a1_con_dos_errores_resumen_con_enlaces_y_el_foco_en_el_resumen():
    html = _render(FORMULARIO, errores={"a": "Escribe el título.", "b": "Escribe el número."})
    assert "Hay un problema" in html and 'role="alert"' in html
    assert '<a href="#campo-a">Escribe el título.</a>' in html
    assert '<a href="#campo-b">Escribe el número.</a>' in html
    assert html.count("autofocus") == 1                     # el del resumen, no el de un campo
    assert html.index("autofocus") < html.index('name="a"')


def test_a1_con_un_error_sin_resumen_y_el_foco_en_el_campo():
    html = _render(FORMULARIO, errores={"b": "Escribe el número."})
    assert "Hay un problema" not in html
    assert ('<input name="b" id="campo-b" aria-invalid="true" '
            'aria-describedby="error-b ayuda-b" autofocus>') in html


def test_a1_la_ayuda_del_campo_se_conserva_sin_duplicar_el_atributo():
    sin_error = _render(FORMULARIO, errores={})
    assert '<input name="b" aria-describedby="ayuda-b">' in sin_error
    arco = (PLANTILLAS / "arco.html").read_text(encoding="utf-8")
    serie = arco.split('name="serie"', 1)[1].split(">", 1)[0]
    assert "aria-describedby" not in serie                  # lo pone la macro, una sola vez


def test_a1_los_cuatro_formularios_llevan_el_resumen():
    for nombre in ("editar_serie.html", "editar_numero.html", "editar_arco.html", "arco.html"):
        texto = (PLANTILLAS / nombre).read_text(encoding="utf-8")
        assert "{{ ui.resumen_errores(errores, orden_campos) }}" in texto, nombre


def test_a2_el_titulo_de_la_pestana_empieza_por_error():
    base = (PLANTILLAS / "base.html").read_text(encoding="utf-8")
    assert "<title>{% if errores is defined and errores %}Error: {% endif %}" in base


def test_a3_un_campo_vacio_es_una_instruccion():
    assert _titulo("  ")[1] == "Escribe el título."
    assert _titulo("x" * 501)[1] == "El título tiene que tener como mucho 500 caracteres."
    servicio = RAIZ / "src" / "zascarr" / "services" / "edicion_manual.py"
    edicion = servicio.read_text(encoding="utf-8")
    assert "no puede estar vacío" not in edicion and "no puede superar" not in edicion
    assert '"Escribe el título."' in edicion and '"Escribe el número."' in edicion


VETADAS = re.compile(
    r"\b(por favor|lo sentimos|inválid[oa]s?|ups|vaya,|haz clic|pulsa aquí|"
    r"ha ocurrido un error|algo ha ido mal)\b", re.I)


def test_a4_ninguna_palabra_vetada_en_lo_que_se_ve():
    encontradas = []
    for ruta in sorted(PLANTILLAS.glob("*.html")):
        for n, linea in enumerate(_visible(ruta.read_text(encoding="utf-8")).splitlines(), 1):
            if VETADAS.search(linea):
                encontradas.append(f"{ruta.name}:{n}: {linea.strip()[:90]}")
    assert not encontradas, "\n".join(encontradas)


# Sin guion delante ni detrás: `pend-paginas-arriba` es un nombre de clase, no texto que se lea.
POSICION = re.compile(r"(?<![-\w])(arriba|abajo|a la derecha|a la izquierda)(?![-\w])", re.I)


def test_g2_sin_indicaciones_de_posicion_en_lo_que_se_ve():
    encontradas = []
    for ruta in sorted(PLANTILLAS.glob("*.html")):
        for n, linea in enumerate(_visible(ruta.read_text(encoding="utf-8")).splitlines(), 1):
            # «La carpeta de arriba» es la que contiene a otra, no una posición en la pantalla.
            limpia = linea.replace("carpeta de arriba", "")
            if POSICION.search(limpia) and not limpia.lstrip().startswith(("//", "/*", "*")):
                encontradas.append(f"{ruta.name}:{n}: {linea.strip()[:90]}")
    assert not encontradas, "\n".join(encontradas)


def test_f3_una_confirmacion_con_si_no_se_cancela_a_secas():
    for ruta in sorted(PLANTILLAS.glob("*.html")):
        texto = ruta.read_text(encoding="utf-8")
        if re.search(r">\s*Sí, ", texto):
            assert ">Cancelar<" not in texto, ruta.name


def test_reglas_escritas_en_el_sistema_de_diseno():
    ruta = RAIZ / "docs" / "design" / "sistema-de-diseno-zascarr.md"
    sistema = ruta.read_text(encoding="utf-8")
    for regla in ("**Errores de un formulario**", "**Palabras vetadas**",
                  "**Sin indicaciones de posición**",
                  "**Cuánto se espera**", "**Uno por página**", "**Tres alturas**",
                  "**Confirmación con efecto**", "**«Sin resultados» no es «vacío»:**"):
        assert regla in sistema, regla
