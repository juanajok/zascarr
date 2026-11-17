

def test_las_abreviaturas_con_puntos_quedan_juntas_en_el_titulo():
    """Bug 2026-11-16: «DC K.O. #1…» se parseaba como serie «DC K O» y el
    matcher no encontraba la serie «DC K.O.» (acababa en _Unsorted)."""
    from zascarr.utils.naming import parse_comic_filename

    r = parse_comic_filename(
        "DC K.O. #1 - Súbete al ring (Panini) [CRG] {FSPR SC}.cbz")
    assert r.series == "DC KO"
    assert r.issue_number == "1"

    escudo = parse_comic_filename("S.H.I.E.L.D. 001 (2010).cbz")
    assert escudo.series == "SHIELD"


def test_la_serie_parseada_normaliza_igual_que_la_de_la_bd():
    """El match es exacto por `title_norm`: «DC KO» debe normalizar a «dc ko»."""
    from zascarr.core.matcher import normalize_title
    from zascarr.utils.naming import parse_comic_filename

    r = parse_comic_filename("DC K.O. #1 - Súbete al ring (Panini) [CRG].cbz")
    assert normalize_title(r.series) == normalize_title("DC K.O.")
