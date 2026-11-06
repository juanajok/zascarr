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


def _jpeg_con_ruido(ancho: int = 320, alto: int = 480) -> bytes:
    """JPEG grande (~100 KB) para poder cortarlo a mitad del cuerpo, con la cabecera intacta."""
    import random
    azar = random.Random(7)
    img = Image.new("RGB", (ancho, alto))
    img.putdata([(azar.randrange(256), azar.randrange(256), azar.randrange(256))
                 for _ in range(ancho * alto)])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80)
    return buf.getvalue()


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
    def test_un_acierto_no_registra_nada(self, tmp_path):
        """AC-13: la app no filtra por nivel; un evento por petición (también las 304) sería una línea
        por portada de la rejilla. El acierto no emite ningún evento."""
        serie = uuid4()
        _antigua(tmp_path, serie, 320)
        with structlog.testing.capture_logs() as registros:
            assert portada_previa_suficiente(tmp_path, serie).ancho == 320
        assert registros == []

    def test_una_previa_pequena_no_registra_nada(self, tmp_path):
        serie = uuid4()
        _antigua(tmp_path, serie, 100)
        with structlog.testing.capture_logs() as registros:
            portada_previa_suficiente(tmp_path, serie)
        assert registros == []



class TestRuidoEnElRegistro:
    """Se evalúa en CADA petición (también las 304); una rejilla pide cientos de portadas."""

    def test_sin_previa_no_emite_ningun_evento(self, tmp_path):
        """El caso más común (serie sin antigua) no avisa: `FileNotFoundError` no es un fallo."""
        with structlog.testing.capture_logs() as registros:
            assert portada_previa_suficiente(tmp_path, uuid4()) is None
        assert registros == []

    def test_una_previa_ilegible_avisa_una_sola_vez_mientras_no_cambie(self, tmp_path):
        serie = uuid4()
        ruta = tmp_path / f"{serie}.jpg"
        ruta.write_bytes(b"no soy una imagen")
        with structlog.testing.capture_logs() as registros:
            for _ in range(5):
                assert portada_previa_suficiente(tmp_path, serie) is None
        avisos = [r for r in registros if r["event"] == "cover.previa_ilegible"]
        assert len(avisos) == 1 and avisos[0]["motivo"]
        assert str(tmp_path) not in str(registros) and str(serie) not in str(registros)

    def test_si_el_fichero_cambia_vuelve_a_avisar(self, tmp_path):
        serie = uuid4()
        ruta = tmp_path / f"{serie}.jpg"
        ruta.write_bytes(b"no soy una imagen")
        with structlog.testing.capture_logs() as registros:
            portada_previa_suficiente(tmp_path, serie)
            ruta.write_bytes(b"sigo sin ser una imagen, ahora mas largo")
            portada_previa_suficiente(tmp_path, serie)
        assert len([r for r in registros if r["event"] == "cover.previa_ilegible"]) == 2

    def test_la_memoria_de_avisos_esta_acotada(self, tmp_path, monkeypatch):
        monkeypatch.setattr(zcover, "_MAX_ILEGIBLES_AVISADAS", 3)
        zcover._ILEGIBLES_AVISADAS.clear()
        for _ in range(10):
            serie = uuid4()
            (tmp_path / f"{serie}.jpg").write_bytes(b"x")
            portada_previa_suficiente(tmp_path, serie)
        assert len(zcover._ILEGIBLES_AVISADAS) <= 3


class TestJpegTruncado:
    """A-1 de QA: la cabecera de un JPEG cortado a mitad del cuerpo da el ancho de uno entero, pero
    no se decodifica y el navegador la pinta a medias. Sin su marcador final, no cuenta."""

    @pytest.mark.parametrize("corte", [0.6, 0.1, 700])
    def test_una_antigua_cortada_no_cuenta_como_suficiente(self, tmp_path, corte):
        serie = uuid4()
        entero = _jpeg_con_ruido()
        recortado = entero[:corte] if corte > 1 else entero[:int(len(entero) * corte)]
        (tmp_path / f"{serie}.jpg").write_bytes(recortado)
        with Image.open(io.BytesIO(recortado)) as img:
            assert img.width == 320          # la cabecera sola engañaría: da el ancho de uno entero
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_la_misma_imagen_entera_si_cuenta(self, tmp_path):
        serie = uuid4()
        (tmp_path / f"{serie}.jpg").write_bytes(_jpeg_con_ruido())
        assert portada_previa_suficiente(tmp_path, serie).ancho == 320

    @pytest.mark.parametrize("sobrante", [b"\x00", b"\x00" * 16, b"basura"])
    def test_bytes_sobrantes_tras_el_marcador_final_no_cuentan(self, tmp_path, sobrante):
        """AC-08 (v1.1): termina EXACTAMENTE en `FF D9`; cae a la cascada, que es segura."""
        serie = uuid4()
        (tmp_path / f"{serie}.jpg").write_bytes(_jpeg_con_ruido() + sobrante)
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_acabar_en_d9_sin_el_ff_delante_no_cuenta(self, tmp_path):
        """Mutación E4: comprobar solo el byte final `D9` aceptaría una cola que no es un EOI."""
        serie = uuid4()
        entero = _jpeg_con_ruido()
        (tmp_path / f"{serie}.jpg").write_bytes(entero[:-2] + b"\x00\xd9")
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_un_ff_d9_en_mitad_del_fichero_no_basta(self, tmp_path):
        """Una miniatura EXIF lleva su propio EOI en mitad del fichero: solo vale el del final."""
        serie = uuid4()
        entero = _jpeg_con_ruido()
        corte = len(entero) // 2
        con_eoi_en_medio = entero[:corte] + b"\xff\xd9" + entero[corte:corte + 500]
        assert not con_eoi_en_medio.endswith(b"\xff\xd9")
        (tmp_path / f"{serie}.jpg").write_bytes(con_eoi_en_medio)
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_sin_ff_d8_inicial_no_cuenta(self, tmp_path, monkeypatch):
        """Aunque Pillow dijera JPEG y el ancho fuera 400, sin SOI no es una previa válida."""
        serie = uuid4()
        entero = _jpeg_con_ruido()
        (tmp_path / f"{serie}.jpg").write_bytes(b"\x00\x00" + entero[2:])

        class Falsa:
            format, width = "JPEG", 400

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        monkeypatch.setattr(zcover.Image, "open", lambda *a, **k: Falsa())
        assert portada_previa_suficiente(tmp_path, serie) is None

    def test_ancho_comprobacion_y_servido_usan_los_mismos_bytes(self, tmp_path, monkeypatch):
        """Una sola lectura: si el fichero se sustituye tras leerlo (aquí, al abrirlo con Pillow),
        lo devuelto son los bytes que se midieron, no los nuevos."""
        serie = uuid4()
        ruta = _antigua(tmp_path, serie, 320)
        medidos = ruta.read_bytes()
        real_open = zcover.Image.open

        def abrir_y_sustituir(*a, **k):
            imagen = real_open(*a, **k)
            ruta.write_bytes(_jpeg(500))      # el disco cambia a mitad
            return imagen
        monkeypatch.setattr(zcover.Image, "open", abrir_y_sustituir)

        previa = portada_previa_suficiente(tmp_path, serie)

        assert previa.datos == medidos and previa.ancho == 320
        assert ruta.read_bytes() != medidos     # y el fichero sí cambió: la prueba es real

    def test_el_truncado_avisa_una_vez_con_el_tipo_y_sin_ruta(self, tmp_path):
        serie = uuid4()
        entero = _jpeg_con_ruido()
        (tmp_path / f"{serie}.jpg").write_bytes(entero[: len(entero) // 2])
        with structlog.testing.capture_logs() as registros:
            for _ in range(3):
                portada_previa_suficiente(tmp_path, serie)
        avisos = [r for r in registros if r["event"] == "cover.previa_ilegible"]
        assert len(avisos) == 1 and avisos[0]["motivo"] == "PortadaPreviaTruncadaError"
        assert str(tmp_path) not in str(registros) and str(serie) not in str(registros)
