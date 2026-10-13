# ruff: noqa: E501
"""#118 — la pista de tradición que da la carpeta raíz de un grupo (pura, sin base de datos).

Es una PISTA: la tabla es la que usa el importador para organizar (`TRADITION_MAP`), no una decisión. Donde una carpeta
corresponde a más de una tradición («Comics»: americana y británica) se devuelven todas y ninguna se elige."""
from __future__ import annotations

import pytest

from zascarr.models import ComicTradition
from zascarr.services.descubrimiento_grupo import tradiciones_de_la_carpeta
from zascarr.services.importer import TRADITION_MAP


@pytest.mark.parametrize("clave,esperado", [
    ("Comics/Flash (1987)", {"american", "british"}),
    ("comics/flash", {"american", "british"}),            # sin distinguir mayúsculas
    ("BD/Thorgal (1980)", {"franco_belgian"}),
    ("Tebeos", {"tebeo"}),
    ("Manga/One Piece", {"manga", "manhua"}),
    ("Fumetti/Dylan Dog", {"fumetti"}),
])
def test_la_carpeta_raiz_sugiere_las_tradiciones_que_se_guardan_en_ella(clave, esperado):
    assert set(tradiciones_de_la_carpeta(clave)) == esperado


@pytest.mark.parametrize(
    "clave", ["Cosas raras/Flash", ".", "", "_Unsorted/Flash", "ComicsExtra/Flash"])
def test_una_carpeta_desconocida_o_sin_clasificar_no_sugiere_nada(clave):
    assert tradiciones_de_la_carpeta(clave) == []


def test_la_pista_nunca_incluye_otra_y_solo_devuelve_tradiciones_validas():
    for clave in {f"{c}/x" for c in TRADITION_MAP.values()}:
        assert all(ComicTradition(t) for t in tradiciones_de_la_carpeta(clave))
        assert ComicTradition.OTHER.value not in tradiciones_de_la_carpeta(clave)
