"""
tests/test_cover.py

Suite de extract_cover_thumbnail (B2: miniaturas en la bandeja de
pendientes). Genera CBZ reales con una imagen mínima vía Pillow en vez de
mockear zipfile/PIL: es la única forma honesta de probar que la
extracción y el redimensionado funcionan de verdad.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from PIL import Image

from zascarr.utils.cover import extract_cover_thumbnail


def make_cbz_with_page(path: Path, size: tuple[int, int] = (600, 900)) -> None:
    img = Image.new("RGB", size, color=(120, 40, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("002.jpg", buf.getvalue())
        zf.writestr("001.jpg", buf.getvalue())  # orden natural: 001 antes que 002


class TestExtractCoverThumbnail:

    def test_extrae_la_primera_pagina_y_la_redimensiona(self, tmp_path):
        path = tmp_path / "comic.cbz"
        make_cbz_with_page(path)

        result = extract_cover_thumbnail(path)

        assert result is not None
        data, content_type = result
        assert content_type == "image/jpeg"
        with Image.open(io.BytesIO(data)) as thumb:
            assert thumb.width <= 240

    def test_extension_no_soportada_devuelve_none(self, tmp_path):
        # CBR requeriría unrar: fuera de alcance (ver docstring del módulo).
        path = tmp_path / "comic.cbr"
        path.write_bytes(b"no importa, ni se llega a abrir")
        assert extract_cover_thumbnail(path) is None

    def test_archivo_inexistente_devuelve_none(self, tmp_path):
        assert extract_cover_thumbnail(tmp_path / "no_existe.cbz") is None

    def test_zip_sin_paginas_de_imagen_devuelve_none(self, tmp_path):
        path = tmp_path / "vacio.cbz"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("ComicInfo.xml", "<ComicInfo></ComicInfo>")
        assert extract_cover_thumbnail(path) is None

    def test_zip_corrupto_devuelve_none(self, tmp_path):
        path = tmp_path / "corrupto.cbz"
        path.write_bytes(b"esto no es un zip")
        assert extract_cover_thumbnail(path) is None


class TestAnchoExplicito:
    """BL-PORT1 (#300, AC-01/AC-05): el ancho se pide explícitamente (240 «Por revisar»,
    600 serie) y NUNCA se amplía un original más pequeño."""

    def test_ancho_explicito_600(self, tmp_path):
        path = tmp_path / "comic.cbz"
        make_cbz_with_page(path, size=(1600, 2400))

        result = extract_cover_thumbnail(path, ancho=600)

        assert result is not None
        data, content_type = result
        assert content_type == "image/jpeg"
        with Image.open(io.BytesIO(data)) as thumb:
            assert thumb.width == 600
            assert abs(thumb.height - 900) <= 1

    def test_por_defecto_sigue_en_240(self, tmp_path):
        """FR-17: «Por revisar» no cambia aunque exista el ancho de serie."""
        path = tmp_path / "comic.cbz"
        make_cbz_with_page(path, size=(1600, 2400))

        result = extract_cover_thumbnail(path)

        assert result is not None
        with Image.open(io.BytesIO(result[0])) as thumb:
            assert thumb.width == 240

    def test_original_pequeno_no_se_amplia(self, tmp_path):
        path = tmp_path / "pequeno.cbz"
        make_cbz_with_page(path, size=(400, 600))

        result = extract_cover_thumbnail(path, ancho=600)

        assert result is not None
        with Image.open(io.BytesIO(result[0])) as thumb:
            assert thumb.width == 400
            assert thumb.height == 600
