"""
tests/test_fs.py

Suite de utils/fs.py (A3): safe_move nunca daña la colección — no
sobreescribe destinos ocupados, no borra el original hasta que la copia
está verificada — y sanitize_segment impide que un título escape de la
biblioteca al construir la ruta canónica.
"""
from __future__ import annotations

import errno

import pytest

from zascarr.utils import fs
from zascarr.utils.fs import safe_move, sanitize_segment


class TestSanitizeSegment:

    def test_barra_se_convierte_en_espacio(self):
        assert sanitize_segment("Batman/Superman") == "Batman Superman"
        assert sanitize_segment("Batman\\Superman") == "Batman Superman"

    def test_punto_punto_no_escapa(self):
        assert sanitize_segment("..") == "_Serie"
        assert sanitize_segment("../x") == "x"

    def test_vacio_o_none_da_segmento_seguro(self):
        assert sanitize_segment("") == "_Serie"
        assert sanitize_segment(None) == "_Serie"

    def test_titulo_normal_intacto(self):
        assert sanitize_segment("Batman") == "Batman"

    def test_titulo_larguisimo_se_trunca_bajo_el_limite(self):
        result = sanitize_segment("a" * 300)
        assert len(result.encode("utf-8")) <= 240


class TestSafeMove:

    def test_mueve_el_archivo(self, tmp_path):
        src = tmp_path / "a.cbz"
        src.write_bytes(b"hola")
        dest = tmp_path / "sub" / "b.cbz"

        result = safe_move(src, dest)

        assert result == dest
        assert dest.read_bytes() == b"hola"
        assert not src.exists()

    def test_no_sobreescribe_destino_ocupado(self, tmp_path):
        src = tmp_path / "a.cbz"
        src.write_bytes(b"nuevo")
        dest = tmp_path / "b.cbz"
        dest.write_bytes(b"antiguo")

        result = safe_move(src, dest)

        # el destino ya existente queda intacto...
        assert dest.read_bytes() == b"antiguo"
        # ...y el nuevo aterriza con un nombre único
        assert result != dest
        assert result.read_bytes() == b"nuevo"
        assert not src.exists()

    def test_destino_ocupado_sufijo_unico_progresivo(self, tmp_path):
        src = tmp_path / "a.cbz"
        src.write_bytes(b"x")
        (tmp_path / "b.cbz").write_bytes(b"0")
        (tmp_path / "b (1).cbz").write_bytes(b"1")

        result = safe_move(src, tmp_path / "b.cbz")

        assert result.name == "b (2).cbz"
        assert result.read_bytes() == b"x"

    def test_mismo_archivo_no_hace_nada(self, tmp_path):
        p = tmp_path / "a.cbz"
        p.write_bytes(b"x")

        assert safe_move(p, p) == p
        assert p.read_bytes() == b"x"

    def test_extension_compuesta_conserva_el_sufijo_completo(self, tmp_path):
        src = tmp_path / "a.cbz"
        src.write_bytes(b"x")
        dest = tmp_path / "archive.tar.gz"
        dest.write_bytes(b"antiguo")

        result = safe_move(src, dest)

        # conserva ".tar.gz" entero: "archive (1).tar.gz", no "archive.tar (1).gz"
        assert result.name == "archive (1).tar.gz"
        assert dest.read_bytes() == b"antiguo"
        assert result.read_bytes() == b"x"

    def test_copia_fallida_preserva_el_original(self, tmp_path, monkeypatch):
        """A3: si la copia entre discos falla, el original queda intacto."""
        src = tmp_path / "a.cbz"
        src.write_bytes(b"original")

        def boom(*_a, **_k):
            raise OSError("disco lleno")

        # forzar la rama de disco-distinto (la que copia y verifica)
        monkeypatch.setattr(fs, "_same_filesystem", lambda s, d: False)
        monkeypatch.setattr(fs.shutil, "copy2", boom)

        with pytest.raises(OSError, match="disco lleno"):
            safe_move(src, tmp_path / "b.cbz")

        assert src.exists()
        assert src.read_bytes() == b"original"
        # el temporal a medias no debe quedar en el directorio destino
        assert list(tmp_path.iterdir()) == [src]

    def test_exdev_con_mismo_st_dev_cae_a_copia_entre_discos(self, tmp_path, monkeypatch):
        """Hallazgo E2E release 1.0: dos bind mounts distintos del mismo
        filesystem host reportan el mismo st_dev dentro de un contenedor
        Docker, pero el kernel rechaza rename() entre ellos con EXDEV. Antes
        de este fix, safe_move confiaba ciegamente en _same_filesystem() y
        dejaba escapar el OSError, tumbando el importador al 100% con el
        docker-compose.yml real."""
        src = tmp_path / "a.cbz"
        src.write_bytes(b"contenido")
        dest = tmp_path / "sub" / "b.cbz"

        # _same_filesystem() dice "mismo disco" (como con dos bind mounts),
        # pero el os.replace() real se comporta como si cruzara un mount.
        monkeypatch.setattr(fs, "_same_filesystem", lambda s, d: True)
        original_replace = fs.os.replace
        calls = {"n": 0}

        def replace_primero_exdev(src_arg, dest_arg):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            return original_replace(src_arg, dest_arg)

        monkeypatch.setattr(fs.os, "replace", replace_primero_exdev)

        result = safe_move(src, dest)

        assert result == dest
        assert dest.read_bytes() == b"contenido"
        assert not src.exists()

    def test_exdev_no_enmascara_otros_oserror(self, tmp_path, monkeypatch):
        """Solo EXDEV cae al camino de discos distintos; cualquier otro
        OSError (disco lleno, permiso denegado...) debe propagarse tal cual."""
        src = tmp_path / "a.cbz"
        src.write_bytes(b"x")
        dest = tmp_path / "b.cbz"

        monkeypatch.setattr(fs, "_same_filesystem", lambda s, d: True)

        def replace_permiso_denegado(*_a, **_k):
            raise OSError(errno.EACCES, "Permission denied")

        monkeypatch.setattr(fs.os, "replace", replace_permiso_denegado)

        with pytest.raises(OSError, match="Permission denied"):
            safe_move(src, dest)

        assert src.exists()
