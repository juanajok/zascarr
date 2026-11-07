"""BL-ETQ1a: normalización, validación y precedencia de etiquetas (sin red)."""
from __future__ import annotations

import pytest

from zascarr.services.etiquetas import (
    EtiquetaInvalida,
    normalize_tag,
    puede_escribir,
    validar_nombre,
)


@pytest.mark.parametrize("entrada,esperado", [
    ("Noir", "noir"),
    ("Nóir", "noir"),
    ("The Walking Dead", "the walking dead"),
    ("S.H.I.E.L.D.", "s h i e l d"),
    ("space--opera", "space opera"),
    ("  Aventuras  ", "aventuras"),
])
def test_normaliza_como_la_funcion_sql(entrada, esperado):
    assert normalize_tag(entrada) == esperado


def test_validar_conserva_espacios_internos_y_rechaza_vacios():
    assert validar_nombre("  The Walking Dead ") == ("The Walking Dead", "the walking dead")
    with pytest.raises(EtiquetaInvalida):
        validar_nombre("  ")
    with pytest.raises(EtiquetaInvalida):
        validar_nombre("a" * 65)
    with pytest.raises(EtiquetaInvalida):
        validar_nombre("noir, escuela")
    with pytest.raises(EtiquetaInvalida):
        validar_nombre("noir\n escuela")


def test_manual_no_se_pisa_por_una_fuente():
    assert puede_escribir({"source": "manual"}, "manual") is True
    assert puede_escribir({"source": "manual"}, "comicinfo_xml") is False
    assert puede_escribir({"source": "comicinfo_xml"}, "comicinfo_xml") is True
