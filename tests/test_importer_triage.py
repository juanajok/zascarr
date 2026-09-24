"""
tests/test_importer_triage.py

Endurecimiento del parseo de ComicInfo.xml (P1 del audit):
  - XML válido se parsea sin sorpresas.
  - XML malformado lanza ParseError (que triage() captura como warning).
  - Entidades externas (XXE) no se resuelven: o bien ParseError, o bien parseo
    SIN fugar contenido de archivos.
  - ComicInfo.xml descomprimido > MAX_COMICINFO_BYTES se ignora (DoS/ZIP bomb).
"""
from __future__ import annotations

import zipfile
from xml.etree import ElementTree

import pytest

from zascarr.core.importer_triage import (
    MAX_COMICINFO_BYTES, parse_comic_info, triage,
)


class TestParseComicInfo:

    def test_basico_extrae_campos(self):
        xml = ("<ComicInfo><Series>Batman</Series><Number>12</Number>"
               "<Year>2011</Year><Writer>Autor</Writer></ComicInfo>")
        info = parse_comic_info(xml.encode("utf-8"))

        assert info.series == "Batman"
        assert info.number == "12"
        assert info.year == 2011
        assert info.credits["writer"] == ["Autor"]

    def test_malformado_lanza_parse_error(self):
        with pytest.raises(ElementTree.ParseError):
            parse_comic_info(b"<ComicInfo><Series>sin cerrar</ComicInfo>")

    def test_no_resuelve_entidad_externa(self):
        """XXE: una entidad SYSTEM a file:///etc/passwd no debe fugarse."""
        xml = ('<?xml version="1.0"?><!DOCTYPE ComicInfo ['
               '<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
               '<ComicInfo><Series>&xxe;</Series></ComicInfo>').encode("utf-8")
        try:
            info = parse_comic_info(xml)
        except ElementTree.ParseError:
            return  # aceptable: triage() lo convierte en "malformado"
        assert "root:" not in (info.series or "")


class TestTriageLimiteTamano:

    def test_comicinfo_demasiado_grande_se_ignora(self, tmp_path):
        cbz = tmp_path / "bomb.cbz"
        # ZIP_DEFLATED: el .cbz queda diminuto pero el entry descomprime > 1 MiB
        with zipfile.ZipFile(cbz, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("ComicInfo.xml", "x" * (MAX_COMICINFO_BYTES + 1))

        result = triage(cbz)

        assert result.comic_info is None
        assert any("demasiado grande" in w for w in result.warnings)
