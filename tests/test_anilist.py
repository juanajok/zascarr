"""
tests/test_anilist.py

Bug real, visible en /ui/descubrir: AniList deja "<br>" literal en la
sinopsis aunque se pida "description(asHtml: false)" — Jinja2 lo escapa
a "&lt;br&gt;" en vez de un salto de línea. _clean_description lo
limpia una vez en el origen.
"""
from __future__ import annotations

from zascarr.services.anilist import _clean_description


class TestCleanDescription:

    def test_br_se_convierte_en_salto_de_linea(self):
        result = _clean_description("Hola<br>Mundo")
        assert "<br>" not in result
        assert result == "Hola\nMundo"

    def test_br_autocerrado_y_con_espacios(self):
        result = _clean_description("A<br/>B<br />C<BR>D")
        assert "<br" not in result.lower()
        assert result == "A\nB\nC\nD"

    def test_texto_sin_br_no_cambia(self):
        assert _clean_description("Sin etiquetas.") == "Sin etiquetas."

    def test_none_se_queda_en_none(self):
        assert _clean_description(None) is None

    def test_cadena_vacia_se_queda_vacia(self):
        assert _clean_description("") == ""
