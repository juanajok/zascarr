"""
tests/test_cover_portada_previa.py

#435 (BL-PORT5): `portada_previa_suficiente`, la única regla que decide si una portada previa
(hoy, la caché antigua `covers/<id>.jpg`) tiene resolución suficiente para conservarla. Imágenes
reales en `tmp_path`; el ancho se lee de la cabecera, sin decodificar.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from uuid import uuid4

import pytest
import structlog
from PIL import Image, ImageFile

import zascarr.utils.cover as zcover
from zascarr.utils.cover import (
    UMBRAL_PORTADA_PREVIA_PX,
    portada_previa_suficiente,
    rutas_de_portadas_previas,
)


def _jpeg(ancho: int, alto: int = 40, formato: str = "JPEG") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (ancho, alto), color=(30, 90, 160)).save(buf, format=formato)
    return buf.getvalue()


def _antigua(covers: Path, serie, ancho: int, **kw) -> Path:
    covers.mkdir(parents=True, exist_ok=True)
    ruta = covers / f"{serie}.jpg"
    ruta.write_bytes(_jpeg(ancho, **kw))
    return ruta


class TestUmbral:
    def test_el_umbral_es_300_e_inclusivo(self, tmp_path):
        """AC-03: 300 px es suficiente y 299 no."""
        assert UMBRAL_PORTADA_PREVIA_PX == 300
        s1, s2 = uuid4(), uuid4()
        _antigua(tmp_path, s1, 300)
        _antigua(tmp_path, s2, 299)
        assert portada_previa_suficiente(tmp_path, s1) is not None
        assert portada_previa_suficiente(tmp_path, s2) is None

    def test_devuelve_los_bytes_el_ancho_y_la_ruta_de_la_portada(self, tmp_path):
        serie = uuid4()
        ruta = _antigua(tmp_path, serie, 320)
        previa = portada_previa_suficiente(tmp_path, serie)
        assert previa.ruta == ruta and previa.ancho == 320
        assert previa.datos == ruta.read_bytes()      # los mismos bytes que se sirven

    def test_100_px_de_tebeosfera_no_basta(self, tmp_path):
        serie = uuid4()
        _antigua(tmp_path, serie, 100, alto=100)
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_sin_antigua_no_hay_previa(self, tmp_path):
        assert portada_previa_suficiente(tmp_path, uuid4()) is None


class TestFallaCerrado:
    """FR-04 / FR-12 / AC-08, AC-16: lo ilegible no cuenta, sin 500 ni rutas en el registro."""

    @pytest.mark.parametrize("contenido", [b"", b"no soy una imagen", _jpeg(400)[:20]])
    def test_vacia_truncada_o_no_imagen(self, tmp_path, contenido):
        serie = uuid4()
        (tmp_path / f"{serie}.jpg").write_bytes(contenido)
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_un_png_con_extension_jpg_no_cuenta(self, tmp_path):
        """Se sirve como image/jpeg: lo que no es JPEG no es una previa válida."""
        serie = uuid4()
        (tmp_path / f"{serie}.jpg").write_bytes(_jpeg(400, formato="PNG"))
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_permiso_denegado_no_lanza_y_registra_solo_el_tipo(self, tmp_path):
        serie = uuid4()
        ruta = _antigua(tmp_path, serie, 400)
        ruta.chmod(0)
        try:
            if os.access(ruta, os.R_OK):
                pytest.skip("el usuario puede leer aunque el fichero no tenga permisos (root)")
            with structlog.testing.capture_logs() as registros:
                assert portada_previa_suficiente(tmp_path, serie) is None
        finally:
            ruta.chmod(0o644)

        assert registros and all("PermissionError" in str(r) for r in registros)
        assert str(tmp_path) not in str(registros) and str(serie) not in str(registros)

    def test_una_bomba_de_descompresion_falla_cerrado(self, tmp_path, monkeypatch):
        """`Image.open` puede lanzar `DecompressionBombError` (no es un OSError): no se escapa."""
        serie = uuid4()
        _antigua(tmp_path, serie, 400)

        def bomba(*a, **k):
            raise Image.DecompressionBombError("demasiados píxeles")
        monkeypatch.setattr(zcover.Image, "open", bomba)
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_la_antigua_enorme_en_bytes_no_se_lee_entera(self, tmp_path):
        """Tope de memoria en la Pi: una antigua mayor que el tope de bytes no cuenta."""
        serie = uuid4()
        ruta = _antigua(tmp_path, serie, 400)
        with open(ruta, "ab") as fh:
            fh.write(b"\0" * (zcover.MAX_BYTES_PORTADA_PREVIA + 1))
        assert portada_previa_suficiente(tmp_path, serie) is None


class TestSoloCabecera:
    def test_el_ancho_se_lee_sin_decodificar(self, tmp_path, monkeypatch):
        """AC-09: si la imagen se decodificara (`load`), esta prueba falla."""
        serie = uuid4()
        _antigua(tmp_path, serie, 640)

        def no_decodificar(self, *a, **k):
            raise AssertionError("se decodificó la imagen")
        monkeypatch.setattr(ImageFile.ImageFile, "load", no_decodificar)
        assert portada_previa_suficiente(tmp_path, serie).ancho == 640


class TestUnaSolaRegla:
    def test_la_lista_de_previas_vive_en_un_sitio_y_hoy_es_solo_la_antigua(self, tmp_path):
        serie = uuid4()
        assert rutas_de_portadas_previas(tmp_path, serie) == [tmp_path / f"{serie}.jpg"]

    def test_con_dos_previas_devuelve_la_primera_suficiente_en_orden(self, tmp_path, monkeypatch):
        """AC-11: #418 añadirá `covers/externa/<id>.jpg` con una línea; el orden manda."""
        serie = uuid4()
        pequena = _antigua(tmp_path, serie, 100)
        externa = tmp_path / "externa" / f"{serie}.jpg"
        externa.parent.mkdir()
        externa.write_bytes(_jpeg(500))
        otra = tmp_path / "otra" / f"{serie}.jpg"
        otra.parent.mkdir()
        otra.write_bytes(_jpeg(900))

        monkeypatch.setattr(zcover, "rutas_de_portadas_previas",
                            lambda covers, s: [pequena, externa, otra])
        previa = portada_previa_suficiente(tmp_path, serie)
        assert previa.ruta == externa and previa.ancho == 500

        monkeypatch.setattr(zcover, "rutas_de_portadas_previas",
                            lambda covers, s: [otra, externa])
        assert portada_previa_suficiente(tmp_path, serie).ruta == otra


class TestRegistro:
    def test_el_evento_lleva_ancho_y_umbral_y_ninguna_ruta(self, tmp_path):
        """AC-13."""
        serie = uuid4()
        _antigua(tmp_path, serie, 320)
        with structlog.testing.capture_logs() as registros:
            portada_previa_suficiente(tmp_path, serie)
        eventos = [r for r in registros if r["event"] == "cover.previa_suficiente"]
        assert len(eventos) == 1
        assert eventos[0]["ancho"] == 320 and eventos[0]["umbral"] == 300
        assert str(tmp_path) not in str(registros) and str(serie) not in str(registros)

    def test_una_previa_pequena_no_registra_el_evento(self, tmp_path):
        serie = uuid4()
        _antigua(tmp_path, serie, 100)
        with structlog.testing.capture_logs() as registros:
            portada_previa_suficiente(tmp_path, serie)
        assert not [r for r in registros if r["event"] == "cover.previa_suficiente"]
