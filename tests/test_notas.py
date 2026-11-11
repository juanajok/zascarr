"""#342/BL-WK4: validación y plantillas de notas (puro)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from zascarr.services.notas import MAX_TEXTO, NotaInvalidaError, normalizar_texto
from zascarr.web.routes import crear_templates


def test_normaliza_trim_y_conserva_saltos():
    assert normalizar_texto("  hola\nmundo  ") == "hola\nmundo"


@pytest.mark.parametrize("texto", ["", "   ", "\n\t", None])
def test_rechaza_vacio(texto):
    with pytest.raises(NotaInvalidaError, match="vacía"):
        normalizar_texto(texto)


def test_rechaza_demasiado_larga():
    with pytest.raises(NotaInvalidaError, match=str(MAX_TEXTO)):
        normalizar_texto("x" * (MAX_TEXTO + 1))


def test_plantilla_numero_escapa_html():
    templates = crear_templates()
    nota = SimpleNamespace(texto="<b>páginas 12-13</b>")
    html = templates.get_template("_nota_numero.html").render(
        series=SimpleNamespace(id=uuid4()), issue=SimpleNamespace(id=uuid4()),
        nota_numero=nota, nota_aviso="")
    assert "<b>páginas" not in html
    assert "&lt;b&gt;páginas 12-13&lt;/b&gt;" in html


def test_plantilla_escapa_html():
    templates = crear_templates()
    nota = SimpleNamespace(texto='<script>alert("x")</script>')
    series = SimpleNamespace(id=uuid4())
    html = templates.get_template("_nota_serie.html").render(
        series=series, nota_serie=nota, notas_numeros=[], nota_aviso="",
        ui=None)
    assert "<script>" not in html
    assert "&lt;script&gt;alert" in html


def test_aviso_de_numero_se_ve_fuera_del_details():
    html = crear_templates().get_template("_nota_numero.html").render(
        series=SimpleNamespace(id=uuid4()), issue=SimpleNamespace(id=uuid4()),
        nota_numero=None, nota_aviso="La nota no puede estar vacía.")
    assert html.index("La nota no puede estar vacía.") < html.index('<details id="nota-numero"')
