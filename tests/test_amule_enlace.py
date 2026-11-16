"""Formulario real del footer de amuleweb para añadir un enlace (bug 2026-11-16)."""
from __future__ import annotations

from zascarr.services.amule import AMuleClient


def test_usa_el_campo_ed2klink_del_footer():
    datos = AMuleClient._datos_de_enlace(
        "ed2k://|file|DC%20K.O.%20%231.cbr|1234|AABBCC|/")
    assert datos["ed2klink"].startswith("ed2k://|file|DC K.O. #1.cbr")
    assert datos["selectcat"] == "all"
    assert datos["Submit"] == "Download link"


def test_desescapa_el_nombre_url_encoded_del_foro_una_sola_vez():
    datos = AMuleClient._datos_de_enlace(
        "ed2k://|file|DC%20K.O.%20%231%20-%20S%C3%BAbete%20al%20ring.cbr|1|H|/")
    assert "DC K.O. #1 - Súbete al ring.cbr" in datos["ed2klink"]
    assert "%20" not in datos["ed2klink"] and "%25" not in datos["ed2klink"]


def test_conserva_los_separadores_del_enlace():
    datos = AMuleClient._datos_de_enlace("ed2k://|file|a.cbr|1|H|/")
    assert datos["ed2klink"].count("|") == 5
