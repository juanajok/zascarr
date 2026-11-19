"""#993: matcher puro por nombre de fichero (nunca por título del hilo)."""
from __future__ import annotations

from uuid import uuid4

from zascarr.models import ComicTradition, Series
from zascarr.services.seguimiento import casar_fichero, elegir_serie, nombres_de_enlaces


def _serie(titulo="Batman", **kw) -> Series:
    return Series(id=uuid4(), title=titulo, tradition=ComicTradition.AMERICAN, **kw)


def test_no_casa_recopilatorios_que_el_parser_no_marca_como_edicion():
    serie = Series(id=uuid4(), title="One Piece", tradition=ComicTradition.AMERICAN)
    assert casar_fichero("One Piece 01 - Edición 3 en 1 (Planeta).cbr", serie, set()) is None
    assert casar_fichero("One Piece 1100.cbz", serie, set()) == 1100


def test_casa_numero_por_nombre_de_fichero():
    assert casar_fichero("Batman Vol. 3 012.cbz", _serie(), set()) == 12
    assert casar_fichero("Batman #12.cbz", _serie(), set()) == 12


def test_alias_local_valido_y_titulo_parecido_no_casa():
    serie = _serie("X-Men")
    assert casar_fichero("La Patrulla-X 012.cbz", serie, {"La Patrulla-X"}) == 12
    assert casar_fichero("Batman Beyond 012.cbz", _serie("Batman"), set()) is None


def test_tomos_anuales_especiales_y_numeros_no_enteros_quedan_fuera():
    serie = _serie()
    assert casar_fichero("Batman Tomo 3.cbz", serie, set()) is None
    assert casar_fichero("Batman Annual 1.cbz", serie, set()) is None
    assert casar_fichero("Batman Especial 1.cbz", serie, set()) is None
    assert casar_fichero("Batman 1.5.cbz", serie, set()) is None
    assert casar_fichero("Batman #0.cbz", serie, set()) == 0


def test_ambiguedad_no_elige_serie():
    a, b = _serie("Batman"), _serie("Batman")
    elegido = elegir_serie("Batman 012.cbz", [a, b], {a.id: set(), b.id: set()})
    assert elegido is None


def test_nombres_de_enlaces_ed2k_y_magnet():
    nombres = nombres_de_enlaces(
        ["ed2k://|file|Batman%20012.cbz|123|ABC|/"],
        ["magnet:?xt=urn:btih:abc&dn=Batman%20013.cbz"],
    )
    assert nombres == ["Batman 012.cbz", "Batman 013.cbz"]
