"""El contenedor crea carpetas y archivos con escritura de grupo (el grupo del disco compartido)."""
from __future__ import annotations

import os
import stat
from pathlib import Path

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
