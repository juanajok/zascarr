"""B2a: cerrojo de admisión entre procesos reales (no es el de operaciones)."""
from __future__ import annotations

import os
import stat
import time

from deploy.ops.admision_ops4 import liberar_admision, tomar_admision


def test_admision_crea_fichero_0600_y_es_exclusiva(tmp_path) -> None:
    ruta = tmp_path / "admision.lock"
    fd = tomar_admision(ruta)
    assert isinstance(fd, int) and fd >= 0
    assert stat.S_IMODE(ruta.stat().st_mode) == 0o600
    liberar_admision(fd)
    fd2 = tomar_admision(ruta)
    assert isinstance(fd2, int)
    liberar_admision(fd2)


def test_dos_procesos_no_toman_la_admision_a_la_vez(tmp_path) -> None:
    ruta = tmp_path / "admision.lock"
    lectura, escritura = os.pipe()
    pid = os.fork()
    if pid == 0:  # hijo: toma y avisa; el padre intenta mientras sigue vivo
        os.close(lectura)
        fd = tomar_admision(ruta)
        os.write(escritura, b"1" if fd is not None else b"0")
        time.sleep(1.5)
        if fd is not None:
            liberar_admision(fd)
        os._exit(0)
    os.close(escritura)
    assert os.read(lectura, 1) == b"1"
    assert tomar_admision(ruta) is None
    os.waitpid(pid, 0)
    fd = tomar_admision(ruta)
    assert isinstance(fd, int)
    liberar_admision(fd)
