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


def test_destino_ocupado_no_se_sobrescribe_y_conserva_original(tmp_path):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    destino = raiz / "Uno.cbz"
    destino.write_bytes(b"ajeno")
    final = safe_move_en_raiz(origen, destino, raiz)
    assert final == raiz / "Uno (1).cbz"
    assert not origen.exists() and destino.read_bytes() == b"ajeno"
    assert final.read_bytes() == b"contenido" and final.is_relative_to(raiz)


def test_carrera_de_raiz_swap_a_symlink_falla_cerrada(tmp_path, monkeypatch):
    import os
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    real_open = os.open
    swapped = False

    def abre_raiz(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and str(path) == str(raiz.resolve()):
            swapped = True
            raiz.rename(tmp_path / "raiz-vieja")
            raiz.symlink_to(fuera, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("zascarr.utils.fs.os.open", abre_raiz)
    with pytest.raises(DestinoFueraDeRaizError):
        safe_move_en_raiz(origen, raiz / "Uno.cbz", raiz)
    assert origen.exists() and not list(fuera.rglob("*.cbz"))


def test_swap_del_directorio_padre_de_la_raiz_falla_cerrada(tmp_path, monkeypatch):
    import os
    base = tmp_path / "base"
    parent = base / "parent"
    root = parent / "root"
    root.mkdir(parents=True)
    fuera = tmp_path / "outside_parent"
    (fuera / "root").mkdir(parents=True)
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    real_open = os.open
    swapped = False

    def abre_raiz(path, flags, *args, **kwargs):
        nonlocal swapped
        if not swapped and str(path) == str(root.resolve()):
            swapped = True
            parent.rename(base / "parent-viejo")
            (base / "parent").symlink_to(fuera, target_is_directory=True)
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr("zascarr.utils.fs.os.open", abre_raiz)
    with pytest.raises(DestinoFueraDeRaizError):
        safe_move_en_raiz(origen, root / "Uno.cbz", root)
    assert origen.exists() and not list(fuera.rglob("*.cbz"))


def test_temporal_sustituido_no_publica_ajeno_y_se_limpia_sin_borrarlo(tmp_path):
    from zascarr.utils.fs import copiar_en_raiz, eliminar_en_raiz, publicar_en_raiz
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    temp = raiz / "temporal.part"
    copia = copiar_en_raiz(origen, temp, raiz)
    try:
        temp.unlink()
        temp.write_bytes(b"AJENO")
        destino = raiz / "final.cbz"
        with pytest.raises(DestinoFueraDeRaizError):
            publicar_en_raiz(temp, destino, raiz, fd=copia.fd,
                             inodo_esperado=(copia.st_dev, copia.st_ino))
        assert not destino.exists()
        assert temp.read_bytes() == b"AJENO"            # no se borra el ajeno
        assert not eliminar_en_raiz(temp, raiz,
                                    inodo_esperado=(copia.st_dev, copia.st_ino))
        assert temp.read_bytes() == b"AJENO"
    finally:
        copia.cerrar()


def test_temporal_sobrescrito_in_place_no_publica_ajeno(tmp_path):
    from zascarr.utils.fs import copiar_en_raiz, publicar_en_raiz
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    temp = raiz / "temporal.part"
    copia = copiar_en_raiz(origen, temp, raiz)
    try:
        temp.write_bytes(b"AJENO")
        with pytest.raises(DestinoFueraDeRaizError):
            publicar_en_raiz(temp, raiz / "final.cbz", raiz, fd=copia.fd,
                             inodo_esperado=(copia.st_dev, copia.st_ino),
                             sha256_esperado=copia.sha256)
        assert not (raiz / "final.cbz").exists()
        assert temp.read_bytes() == b"AJENO"
    finally:
        copia.cerrar()


def test_fallo_al_verificar_raiz_no_deja_unbound(tmp_path, monkeypatch):
    raiz = tmp_path / "raiz"
    raiz.mkdir()
    origen = tmp_path / "origen.cbz"
    origen.write_bytes(b"contenido")
    def falla_readlink(_ruta):
        raise OSError("fallo simulado")
    monkeypatch.setattr("zascarr.utils.fs.os.readlink", falla_readlink)
    with pytest.raises(DestinoFueraDeRaizError):
        safe_move_en_raiz(origen, raiz / "Uno.cbz", raiz)
    assert origen.exists()
