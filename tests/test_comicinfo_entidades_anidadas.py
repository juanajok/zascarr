"""El ComicInfo.xml viene de terceros: las entidades anidadas («billion laughs») no se expanden.

Los dos parsers (`importer_triage.parse_comic_info` y `comicinfo_write.parsear`) usan ElementTree
sin `defusedxml` (dictamen SecOps del hallazgo S314). Lo que los protege de esta carga NO es el
tope de tamaño (el payload ocupa ~600 bytes) sino expat ≥ 2.4.1, que corta la amplificación. Esta
prueba es el detector: si un cambio de imagen base o de Python trajera un expat sin ese límite,
falla aquí antes de llegar a la Pi.
"""
from __future__ import annotations

import pyexpat
from xml.etree import ElementTree

import pytest

from zascarr.core.comicinfo_write import ComicInfoInvalidoError, parsear
from zascarr.core.importer_triage import parse_comic_info


def _risas(niveles: int = 9) -> bytes:
    entidades = '<!ENTITY a0 "risaaaaaaaaa">' + "".join(
        f'<!ENTITY a{i} "{f"&a{i - 1};" * 10}">' for i in range(1, niveles + 1))
    return (f'<?xml version="1.0"?><!DOCTYPE ComicInfo [{entidades}]>'
            f"<ComicInfo><Series>&a{niveles};</Series></ComicInfo>").encode()


def test_el_payload_es_pequeno_el_tope_de_tamano_no_lo_para():
    assert len(_risas()) < 1024


def test_expat_tiene_limite_de_amplificacion():
    mayor, menor, parche = (int(x) for x in pyexpat.EXPAT_VERSION.removeprefix("expat_").split("."))
    assert (mayor, menor, parche) >= (2, 4, 1), pyexpat.EXPAT_VERSION


def test_el_importer_no_expande_las_entidades():
    with pytest.raises(ElementTree.ParseError, match="amplification"):
        parse_comic_info(_risas())


def test_el_tagger_no_expande_las_entidades():
    with pytest.raises(ComicInfoInvalidoError, match="amplification"):
        parsear(_risas())
