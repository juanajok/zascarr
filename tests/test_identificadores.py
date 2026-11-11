"""BL-R5 (#234): validación de forma de identificadores, sin red."""
from __future__ import annotations

import pytest

from zascarr.models import MetadataSource
from zascarr.services.identificadores import (
    IdentificadorInvalidoError,
    parsear_identificador,
)


@pytest.mark.parametrize("texto,fuente,valor", [
    ("4050-12345", MetadataSource.COMIC_VINE, "12345"),
    ("cv:4050-12345", MetadataSource.COMIC_VINE, "12345"),
    ("cv:12345", MetadataSource.COMIC_VINE, "12345"),
    ("https://comicvine.gamespot.com/volume/4050-12345/", MetadataSource.COMIC_VINE, "12345"),
    ("gcd:6789", MetadataSource.GCD, "6789"),
    ("https://www.comics.org/series/6789/", MetadataSource.GCD, "6789"),
    ("tb:superman-vol2", MetadataSource.TEBEOSFERA, "superman-vol2"),
    ("https://www.tebeosfera.com/colecciones/superman_vol2.html", MetadataSource.TEBEOSFERA,
     "superman_vol2"),
    ("al:99", MetadataSource.ANILIST, "99"),
    ("https://anilist.co/manga/99/", MetadataSource.ANILIST, "99"),
])
def test_parsea_los_enlaces_y_prefijos_soportados(texto, fuente, valor):
    ident = parsear_identificador(texto)
    assert ident.fuente is fuente and ident.valor == valor


@pytest.mark.parametrize("texto", [
    "",
    "12345",                       # sin fuente es ambiguo
    "978-84-1234-567-8",           # ISBN no es id de serie
    "https://example.com/serie/1",  # fuente no soportada
    "https://www.comics.org/issue/123/",  # no es de serie
    "cv:no",
])
def test_rechaza_formas_invalidas_sin_red(texto):
    with pytest.raises(IdentificadorInvalidoError):
        parsear_identificador(texto)
