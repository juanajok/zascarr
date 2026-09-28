"""B6 — núcleo puro: precedencia por campo y fusión del XML.

Sin BD y sin disco: aquí se comprueba **la decisión** (qué se cambia, qué se
conserva, qué no se inventa) que la ficha `docs/design/benchmark-B6-comicinfo.md`
exige poder previsualizar antes de tocar la colección.
"""
from __future__ import annotations

import pytest

from zascarr.core.comicinfo_write import (
    Accion,
    CampoPlan,
    hay_cambios,
    leer_campos,
    plan,
)

DESEADOS = {
    "Series": "Thorgal",
    "Number": "1",
    "Volume": "1",
    "Year": "1980",
    "Publisher": "Distrinovel",
    "Summary": "Resumen de ZascArr",
    "LanguageISO": None,
}


def _por_tag(campos) -> dict[str, Accion]:
    return {c.tag: c.accion for c in campos}


class TestPrecedencia:

    def test_vacio_en_xml_se_rellena(self):
        campos = plan({}, DESEADOS)
        assert _por_tag(campos)["Series"] is Accion.CAMBIA

    def test_igual_ya_coincide(self):
        campos = plan({"Series": "Thorgal"}, DESEADOS)
        assert _por_tag(campos)["Series"] is Accion.YA_COINCIDE

    def test_presente_y_desconocido_se_conserva(self):
        """Lo que escribió una persona (u otra herramienta) no se pisa."""
        campos = plan({"Summary": "Lo escribí yo a mano"}, DESEADOS)
        assert _por_tag(campos)["Summary"] is Accion.CONSERVA

    def test_propio_da_prueba_de_autoria_y_permite_overlay(self):
        campos = plan(
            {"Summary": "Resumen viejo de ZascArr"},
            DESEADOS,
            propio={"Summary": "Resumen viejo de ZascArr"},
        )
        assert _por_tag(campos)["Summary"] is Accion.CAMBIA

    def test_prueba_de_autoria_de_otro_valor_no_autoriza(self):
        """Si el valor cambió desde que ZascArr escribió, alguien lo tocó."""
        campos = plan(
            {"Summary": "Editado a mano después"},
            DESEADOS,
            propio={"Summary": "Resumen viejo de ZascArr"},
        )
        assert _por_tag(campos)["Summary"] is Accion.CONSERVA

    def test_sin_dato_no_se_inventa(self):
        campos = plan({}, {**DESEADOS, "Summary": None, "Publisher": ""})
        acciones = _por_tag(campos)
        assert acciones["Summary"] is Accion.SIN_DATO
        assert acciones["Publisher"] is Accion.SIN_DATO

    def test_sin_dato_conserva_el_year_manual(self):
        campos = plan({"Year": "1979"}, {**DESEADOS, "Year": None})
        assert _por_tag(campos)["Year"] is Accion.SIN_DATO

    def test_language_iso_nunca_se_genera(self):
        """La tradición (manga/tebeo/grapa) no acredita el idioma del ejemplar."""
        campos = plan({}, DESEADOS)
        assert _por_tag(campos)["LanguageISO"] is Accion.SIN_DATO

    @pytest.mark.parametrize("valor", [None, "", "  "])
    def test_language_iso_sin_dato_no_escribe_nada(self, valor):
        campos = plan({}, {**DESEADOS, "LanguageISO": valor})
        assert _por_tag(campos)["LanguageISO"] is Accion.SIN_DATO

    def test_language_iso_existente_es_preservacion(self):
        campos = plan({"LanguageISO": "es"}, DESEADOS)
        assert _por_tag(campos)["LanguageISO"] is Accion.SIN_DATO

    def test_no_overwrite_solo_rellena_vacios(self):
        """--no-overwrite (add missing): ni siquiera con prueba de autoría."""
        campos = plan(
            {"Summary": "Resumen viejo de ZascArr"},
            DESEADOS,
            propio={"Summary": "Resumen viejo de ZascArr"},
            solo_rellenar=True,
        )
        acciones = _por_tag(campos)
        assert acciones["Summary"] is Accion.CONSERVA
        assert acciones["Series"] is Accion.CAMBIA  # el vacío sí se rellena

    def test_hay_cambios_solo_cuenta_cambia(self):
        assert not hay_cambios(plan({}, {**DESEADOS, "Series": None, "Number": None,
                                        "Volume": None, "Year": None,
                                        "Publisher": None, "Summary": None}))
        assert hay_cambios(plan({}, DESEADOS))

    def test_hay_cambios_false_con_bloqueado(self):
        campos = plan({}, DESEADOS)
        bloqueados = [
            CampoPlan(c.tag, Accion.BLOQUEADO, c.actual, c.nuevo) for c in campos
        ]
        assert not hay_cambios(bloqueados)


class TestFusion:

    def _fusionar(self, xml: bytes | None, campos):
        from zascarr.core.comicinfo_write import fusionar_xml

        return fusionar_xml(xml, campos)

    def test_preserva_elementos_desconocidos(self):
        import xml.etree.ElementTree as ET

        original = (
            b"<?xml version='1.0' encoding='utf-8'?>\n"
            b"<ComicInfo><PageCount>22</PageCount>"
            b"<BlackAndWhite>No</BlackAndWhite><Series>Otro</Series></ComicInfo>"
        )
        campos = plan(leer_campos(ET.fromstring(original)), DESEADOS,
                      propio={"Series": "Otro"})
        nuevo = self._fusionar(original, campos)
        root = ET.fromstring(nuevo)
        assert root.findtext("PageCount") == "22"
        assert root.findtext("BlackAndWhite") == "No"
        assert root.findtext("Series") == "Thorgal"

    def test_no_toca_lo_que_se_conserva(self):
        import xml.etree.ElementTree as ET

        original = b"<ComicInfo><Summary>Mio</Summary><Series>Thorgal</Series></ComicInfo>"
        campos = plan(leer_campos(ET.fromstring(original)), DESEADOS)
        nuevo = self._fusionar(original, campos)
        root = ET.fromstring(nuevo)
        assert root.findtext("Summary") == "Mio"
        assert root.findtext("Number") == "1"

    def test_crea_el_arbol_si_no_habia_xml(self):
        import xml.etree.ElementTree as ET

        nuevo = self._fusionar(None, plan({}, DESEADOS))
        root = ET.fromstring(nuevo)
        assert root.tag == "ComicInfo"
        assert root.findtext("Series") == "Thorgal"
        assert root.findtext("LanguageISO") is None

    def test_lleva_declaracion_de_xml(self):
        assert self._fusionar(None, plan({}, DESEADOS)).startswith(b"<?xml")

    def test_raiz_inesperada_no_se_preserva(self):
        """Un XML que no es ComicInfo no se cuela como raíz del resultado."""
        import xml.etree.ElementTree as ET

        campos = plan({}, DESEADOS)
        nuevo = self._fusionar(b"<Otro><X>1</X></Otro>", campos)
        assert ET.fromstring(nuevo).tag == "ComicInfo"
