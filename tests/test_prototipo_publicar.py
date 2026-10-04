# ruff: noqa: E501
"""ADR 0006: publicar un fichero NUNCA reemplaza a otro (sin Postgres).

`os.replace` sustituye en silencio un nombre existente, y comprobar `exists()` antes deja una ventana en
la que otro escritor puede crear el destino. `_publicar` delega la garantía en el núcleo
(`renameat2(RENAME_NOREPLACE)`, o `link` si el sistema de ficheros no lo admite) y, si no hay ninguna,
RECHAZA el montaje.
"""
from __future__ import annotations

import errno
import os

import pytest

import tests.prototipo_asignacion as proto
from tests.prototipo_asignacion import PublicacionNoSoportadaError, _publicar


@pytest.fixture
def par(tmp_path):
    temporal = tmp_path / ".x.part"
    destino = tmp_path / "x.cbz"
    temporal.write_bytes(b"NUEVO")
    return temporal, destino


class TestPublicarSinReemplazar:

    def test_publica_cuando_el_destino_esta_libre(self, par):
        temporal, destino = par
        _publicar(temporal, destino)
        assert destino.read_bytes() == b"NUEVO" and not temporal.exists()

    def test_un_fichero_ajeno_que_ya_esta_no_se_reemplaza(self, par):
        temporal, destino = par
        destino.write_bytes(b"AJENO")
        with pytest.raises(FileExistsError):
            _publicar(temporal, destino)
        assert destino.read_bytes() == b"AJENO" and temporal.read_bytes() == b"NUEVO"

    def test_el_ajeno_que_aparece_justo_antes_de_publicar_tampoco(self, par, monkeypatch):
        """La ventana de la comprobación previa: el ajeno se crea DESPUÉS de cualquier `exists()`."""
        temporal, destino = par
        original = proto._renameat2_noreplace

        def con_intruso(origen, dst):
            dst.write_bytes(b"AJENO")            # otro escritor llega justo aquí
            return original(origen, dst)
        monkeypatch.setattr(proto, "_renameat2_noreplace", con_intruso)
        with pytest.raises(FileExistsError):
            _publicar(temporal, destino)
        assert destino.read_bytes() == b"AJENO"

    def test_sin_renameat2_cae_a_link_y_tampoco_reemplaza(self, par, monkeypatch):
        temporal, destino = par

        def no_soportado(*_a):
            raise OSError(errno.ENOSYS, "renameat2 no disponible")
        monkeypatch.setattr(proto, "_renameat2_noreplace", no_soportado)
        _publicar(temporal, destino)                               # camino libre: publica con link
        assert destino.read_bytes() == b"NUEVO" and not temporal.exists()
        temporal.write_bytes(b"OTRO")
        with pytest.raises(FileExistsError):                       # ocupado: link falla con EEXIST
            _publicar(temporal, destino)
        assert destino.read_bytes() == b"NUEVO"

    def test_si_el_montaje_no_ofrece_ninguna_garantia_se_rechaza_sin_tocar_nada(self, par, monkeypatch):
        temporal, destino = par
        destino.write_bytes(b"AJENO")
        monkeypatch.setattr(proto, "_renameat2_noreplace",
                            lambda *_a: (_ for _ in ()).throw(OSError(errno.EOPNOTSUPP, "no")))
        monkeypatch.setattr(os, "link", lambda *_a: (_ for _ in ()).throw(OSError(errno.EPERM, "sin enlaces")))
        # Con el destino LIBRE: rechaza (no vuelve a «comprobar y reemplazar»)…
        destino.unlink()
        with pytest.raises(PublicacionNoSoportadaError, match="no permite publicar sin reemplazar"):
            _publicar(temporal, destino)
        assert not destino.exists() and temporal.read_bytes() == b"NUEVO"
        # …y con un ajeno presente, igual de intacto.
        destino.write_bytes(b"AJENO")
        with pytest.raises(PublicacionNoSoportadaError):
            _publicar(temporal, destino)
        assert destino.read_bytes() == b"AJENO"

    def test_el_error_inesperado_no_se_confunde_con_falta_de_soporte(self, par, monkeypatch):
        temporal, destino = par
        monkeypatch.setattr(proto, "_renameat2_noreplace",
                            lambda *_a: (_ for _ in ()).throw(OSError(errno.ENOSPC, "disco lleno")))
        with pytest.raises(OSError) as exc:
            _publicar(temporal, destino)
        assert exc.value.errno == errno.ENOSPC and not isinstance(exc.value, PublicacionNoSoportadaError)
