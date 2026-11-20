"""El contenedor crea carpetas y archivos con escritura de grupo (el grupo del disco compartido)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parent.parent / "docker-entrypoint.sh"


def test_el_entrypoint_fija_umask_002_antes_de_ceder_el_proceso():
    """Regresión: con umask 022 las series nacían 2755 y el grupo no podía moverlas ni borrarlas."""
    lineas = [ln.strip() for ln in ENTRYPOINT.read_text(encoding="utf-8").splitlines()]
    assert "umask 002" in lineas
    assert lineas.index("umask 002") < next(
        i for i, ln in enumerate(lineas) if ln.startswith("exec runuser"))


def test_copiar_y_publicar_en_raiz_dejan_escritura_de_grupo_con_cualquier_umask(tmp_path):
    """Regresión de #1155: asignar crea con modos explícitos que la umask no cambia."""
    from zascarr.utils.fs import copiar_en_raiz, publicar_en_raiz

    origen = tmp_path / "descarga.cbz"
    origen.write_bytes(b"contenido")
    raiz = tmp_path / "biblioteca"
    raiz.mkdir()
    for umask in (0o022, 0o002, 0o077):
        previa = os.umask(umask)
        try:
            destino = raiz / f"Serie {umask:o}" / "Especiales" / "n1.cbz"
            temporal = destino.with_name(".n1.cbz.tmp")
            copia = copiar_en_raiz(origen, temporal, raiz)
            try:
                publicar_en_raiz(temporal, destino, raiz, fd=copia.fd,
                                 inodo_esperado=(copia.st_dev, copia.st_ino),
                                 sha256_esperado=copia.sha256)
            finally:
                os.close(copia.fd)
        finally:
            os.umask(previa)
        assert stat.S_IMODE(destino.stat().st_mode) == 0o664, f"archivo, umask {umask:o}"
        for carpeta in (destino.parent, destino.parent.parent):
            modo = stat.S_IMODE(carpeta.stat().st_mode)
            assert modo & stat.S_IWGRP, f"carpeta {carpeta.name}, umask {umask:o}: {modo:o}"


def test_una_carpeta_nueva_conserva_el_setgid_del_padre(tmp_path):
    """El grupo heredado (media) no se pierde al fijar los permisos de la carpeta."""
    from zascarr.utils.fs import _crear_carpeta

    padre = tmp_path / "raiz"
    padre.mkdir()
    padre.chmod(0o2775)
    fd_padre = os.open(padre, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.close(_crear_carpeta("serie", fd_padre))
    finally:
        os.close(fd_padre)
    assert stat.S_IMODE((padre / "serie").stat().st_mode) == 0o2775


def test_mover_en_el_mismo_disco_da_escritura_de_grupo_aunque_el_origen_no_la_tenga(tmp_path):
    """Rama de enlace de `safe_move_en_raiz` (la usa el importador): conservaba el modo."""
    from zascarr.utils.fs import safe_move_en_raiz

    raiz = tmp_path / "biblioteca"
    raiz.mkdir()
    for modo in (0o600, 0o644):
        origen = tmp_path / f"descarga-{modo:o}.cbz"
        origen.write_bytes(b"x")
        origen.chmod(modo)
        destino = safe_move_en_raiz(origen, raiz / f"Serie {modo:o}" / "n1.cbz", raiz)
        assert not origen.exists()
        assert stat.S_IMODE(destino.stat().st_mode) == 0o664, oct(modo)
        assert stat.S_IMODE(destino.parent.stat().st_mode) & stat.S_IWGRP


def test_mover_a_otro_montaje_da_escritura_de_grupo(tmp_path, monkeypatch):
    """Rama de copia (EXDEV): el archivo final sale 0664 y no queda temporal."""
    from zascarr.utils import fs

    raiz = tmp_path / "biblioteca"
    raiz.mkdir()
    origen = tmp_path / "descarga.cbz"
    origen.write_bytes(b"contenido")
    origen.chmod(0o600)

    def _exdev(*a, **k):
        raise OSError(fs.errno.EXDEV, "otro dispositivo")

    link_real = os.link
    monkeypatch.setattr(fs.os, "link", lambda *a, **k: link_real(*a, **k)
                        if "/proc/self/fd" in str(a[0]) else _exdev())
    destino = fs.safe_move_en_raiz(origen, raiz / "Serie" / "n1.cbz", raiz)
    assert stat.S_IMODE(destino.stat().st_mode) == 0o664
    assert [p.name for p in destino.parent.iterdir()] == ["n1.cbz"]
    assert not origen.exists()


def test_el_temporal_sigue_0600_hasta_verificar_y_un_sha_malo_no_lo_abre(tmp_path, monkeypatch):
    """N-1 (SecOps): el temporal es privado hasta verificar; con sha malo nunca llega a 0664."""
    from zascarr.utils import fs

    origen = tmp_path / "descarga.cbz"
    origen.write_bytes(b"contenido")
    raiz = tmp_path / "biblioteca"
    raiz.mkdir()
    temporal = raiz / "Serie" / ".n1.tmp"
    modos_al_abrir: list[int] = []
    fchmod_real = os.fchmod

    def _espia(fd, modo):
        modos_al_abrir.append(stat.S_IMODE(os.fstat(fd).st_mode))
        return fchmod_real(fd, modo)

    monkeypatch.setattr(fs.os, "fchmod", _espia)
    with pytest.raises(OSError, match="sha256"):
        fs.copiar_en_raiz(origen, temporal, raiz, sha256="0" * 64)
    assert not temporal.exists()
    assert 0o664 not in modos_al_abrir[-1:]            # el fchmod de archivo no se llegó a ejecutar
    copia = fs.copiar_en_raiz(origen, temporal, raiz)
    try:
        assert modos_al_abrir[-1] == 0o600              # hasta verificar, privado
        assert stat.S_IMODE(os.fstat(copia.fd).st_mode) == 0o664
    finally:
        os.close(copia.fd)
