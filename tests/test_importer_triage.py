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

from zascarr.core import importer_triage
from zascarr.core.importer_triage import (
    MAX_COMICINFO_BYTES, MAX_ZIP_ENTRIES, parse_comic_info, triage,
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

    def test_zip_con_demasiadas_entradas_se_ignora(self, tmp_path):
        cbz = tmp_path / "many.cbz"
        with zipfile.ZipFile(cbz, "w") as z:
            for i in range(MAX_ZIP_ENTRIES + 1):
                z.writestr(f"p{i:04d}.jpg", b"")

        result = triage(cbz)

        assert any("demasiadas entradas" in w for w in result.warnings)

    def test_zip_demasiado_grande_descomprimido_se_ignora(self, tmp_path, monkeypatch):
        # Reducir el umbral para no materializar 500 MiB en el test.
        monkeypatch.setattr(importer_triage, "MAX_ZIP_UNCOMPRESSED", 10)
        cbz = tmp_path / "big.cbz"
        with zipfile.ZipFile(cbz, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("page001.jpg", b"x" * 100)

        result = triage(cbz)

        assert any("demasiado grande descomprimido" in w for w in result.warnings)


class TestHashPorFormato:
    """Bug real (2026-09-25, encontrado verificando B16 en vivo): triage()
    salía antes de calcular el sha256 para todo lo que no fuera .cbz/.zip,
    así que ningún .cbr tenía hash y la deduplicación de B3 no funcionaba
    con ellos. En una tebeoteca española típica, que es mayoritariamente
    CBR, no funcionaba casi nunca y además en silencio.

    Leer ComicInfo.xml sí exige descomprimir el RAR (y por eso el CBR
    sigue yendo a Capa 1); hashear no depende del formato."""

    def test_cbr_tiene_hash_aunque_no_se_pueda_abrir(self, tmp_path):
        cbr = tmp_path / "Astérix 01 [CRG].cbr"
        cbr.write_bytes(b"contenido que no es un rar de verdad")

        result = triage(cbr)

        assert result.sha256 is not None
        assert len(result.sha256) == 64
        assert any("solo por filename" in w for w in result.warnings)

    def test_dos_cbr_identicos_dan_el_mismo_hash(self, tmp_path):
        """Es justo lo que necesita el dedupe: el mismo tebeo en dos
        carpetas debe colisionar."""
        (tmp_path / "a").mkdir()
        (tmp_path / "b").mkdir()
        (tmp_path / "a/Superman 011.cbr").write_bytes(b"identico")
        (tmp_path / "b/Superman 011.cbr").write_bytes(b"identico")

        assert triage(tmp_path / "a/Superman 011.cbr").sha256 == \
               triage(tmp_path / "b/Superman 011.cbr").sha256

    def test_cbr_distintos_dan_hashes_distintos(self, tmp_path):
        (tmp_path / "uno.cbr").write_bytes(b"AAAA")
        (tmp_path / "dos.cbr").write_bytes(b"BBBB")

        assert triage(tmp_path / "uno.cbr").sha256 != triage(tmp_path / "dos.cbr").sha256
