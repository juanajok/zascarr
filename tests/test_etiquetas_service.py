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
    # Letras que `unaccent` translitera y NFKD no descompone: sin la tabla,
    # Python las borraba y no coincidía con el `name_norm` de la BD.
    ("ø", "o"), ("Ø", "o"),
    ("æ", "ae"), ("Æ", "ae"),
    ("œ", "oe"), ("Œ", "oe"),
    ("ß", "ss"), ("ẞ", "ss"),
    ("ł", "l"), ("Ł", "l"),
    ("đ", "d"), ("Đ", "d"),
    ("ð", "d"), ("Ð", "d"),
    ("þ", "th"), ("Þ", "th"),
    ("ı", "i"), ("ħ", "h"), ("Ħ", "h"),
    ("ŋ", "n"), ("Ŋ", "n"), ("ŧ", "t"), ("Ŧ", "t"), ("ĸ", "q"),
    ("Smørrebrød", "smorrebrod"),
    ("Æon Flux", "aeon flux"),
    ("Straße", "strasse"),
    ("Łódź", "lodz"),
    ("Đà Nẵng", "da nang"),
    ("Þór", "thor"),
    ("Mjølnir", "mjolnir"),
    ("Ħal Qormi", "hal qormi"),
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


def test_expresion_and_exclusion_y_topes():
    from zascarr.services.etiquetas import MAX_TOKENS, parse_expresion

    e = parse_expresion("noir -escuela Nóir")
    assert e.positivas == ("noir",)
    assert e.negativas == ("escuela",)
    assert parse_expresion("noir " + " ".join(f"t{i}" for i in range(20))).avisos
    assert len(parse_expresion(" ".join(f"t{i}" for i in range(20))).positivas) == MAX_TOKENS
    assert parse_expresion("x" * 150).avisos
