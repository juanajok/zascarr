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

import hashlib
import tracemalloc
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


class TestTriageNoCargaElCbzEnRam:
    """Hallazgo del ensayo con la biblioteca real (2026-10-01): 11 `.cbz` de más
    de 400 MB (el mayor, un integral de 1,2 GB). `triage` los cargaba ENTEROS en
    un `BytesIO` para hashear y abrir el zip de una sola lectura; con el límite
    de 512 MB del contenedor, el kernel mata el proceso al llegar a ellos — y
    la Pi comparte RAM con Transmission, aMule, Prowlarr y Kavita.

    El hash va en streaming y el `ZipFile` se abre desde la ruta (solo lee el
    directorio central y la primera página), así que la memoria no depende del
    tamaño del fichero. Se mide el pico con `tracemalloc`: no depende de la
    velocidad del disco ni de cuánta RAM tenga la máquina de pruebas."""

    TAMANO_BLOB = 40 * 1024 * 1024

    def _cbz_grande(self, ruta):
        with zipfile.ZipFile(ruta, "w", zipfile.ZIP_STORED) as zf:
            zf.writestr("001.jpg", b"no es una imagen")
            # Entrada que nadie lee en el triaje: solo hace pesado el fichero.
            zf.writestr("anexo.bin", b"\0" * self.TAMANO_BLOB)

    def test_el_pico_de_memoria_no_crece_con_el_tamano_del_fichero(self, tmp_path):
        cbz = tmp_path / "Integral grande.cbz"
        self._cbz_grande(cbz)
        assert cbz.stat().st_size > self.TAMANO_BLOB

        tracemalloc.start()
        try:
            triage(cbz)
            _, pico = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        assert pico < self.TAMANO_BLOB // 4, (
            f"triage llegó a {pico / 1e6:.0f} MB de pico con un CBZ de "
            f"{cbz.stat().st_size / 1e6:.0f} MB: no debe cargarlo entero en RAM"
        )

    def test_el_hash_sigue_siendo_el_del_fichero_entero(self, tmp_path):
        cbz = tmp_path / "Integral grande.cbz"
        self._cbz_grande(cbz)

        esperado = hashlib.sha256(cbz.read_bytes()).hexdigest()

        assert triage(cbz).sha256 == esperado

    def test_un_zip_roto_sigue_sin_hash(self, tmp_path):
        """Contrato previo: de un zip ilegible no se guarda hash (dos descargas
        incompletas casi nunca cortan en el mismo byte)."""
        roto = tmp_path / "roto.cbz"
        roto.write_bytes(b"PK\x03\x04 esto no es un zip de verdad")

        result = triage(roto)

        assert result.sha256 is None
        assert any("zip ilegible" in w for w in result.warnings)
