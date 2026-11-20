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


def test_con_umask_002_carpetas_y_archivos_nacen_con_escritura_de_grupo(tmp_path):
    previa = os.umask(0o002)
    try:
        carpeta = tmp_path / "serie"
        carpeta.mkdir()
        archivo = carpeta / "n1.cbz"
        archivo.write_bytes(b"x")
    finally:
        os.umask(previa)
    assert stat.S_IMODE(carpeta.stat().st_mode) & stat.S_IWGRP
    assert stat.S_IMODE(archivo.stat().st_mode) & stat.S_IWGRP
