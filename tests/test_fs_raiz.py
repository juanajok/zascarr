"""H1: mover un archivo confinado a la raíz, sin seguir symlinks de subdirectorio."""
from __future__ import annotations

import pytest

from zascarr.utils.fs import DestinoFueraDeRaizError, safe_move_en_raiz


def test_symlink_de_subdirectorio_no_desvia_la_escritura(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    (raiz / "Comics").symlink_to(fuera, target_is_directory=True)
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    destino = raiz / "Comics" / "Serie" / "Uno.cbz"
    with pytest.raises(DestinoFueraDeRaizError):
        safe_move_en_raiz(origen, destino, raiz)
    assert origen.exists()
    assert not (fuera / "Serie" / "Uno.cbz").exists()


def test_symlink_final_no_se_sigue(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    fuera = tmp_path / "fuera.cbz"
    fuera.write_bytes(b"ajeno")
    (raiz / "destino.cbz").symlink_to(fuera)
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    with pytest.raises(DestinoFueraDeRaizError):
        safe_move_en_raiz(origen, raiz / "destino.cbz", raiz)
    assert origen.exists() and fuera.read_bytes() == b"ajeno"


def test_subdirectorio_normal_si_se_mueve(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    destino = raiz / "Comics" / "Serie" / "Uno.cbz"
    final = safe_move_en_raiz(origen, destino, raiz)
    assert final == destino and final.is_relative_to(raiz)
    assert final.read_bytes() == b"contenido" and not origen.exists()
