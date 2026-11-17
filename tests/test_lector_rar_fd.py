"""El lector RAR debe heredar el fd del paquete (SEC #344)."""
from __future__ import annotations

import os
import sys

import pytest

from zascarr.utils import lector_rar


@pytest.mark.skipif(sys.platform != "linux", reason="procfs")
def test_ejecutar_hereda_el_fd_indicado(tmp_path):
    archivo = tmp_path / "dato"
    archivo.write_bytes(b"x")
    fd = os.open(archivo, os.O_RDONLY)
    try:
        codigo, _salida, _error = lector_rar._ejecutar(
            ["/bin/sh", "-c", f"test -e /proc/self/fd/{fd}"], home=tmp_path,
            timeout=5, tope_salida=1024, pass_fds=(fd,))
        assert codigo == 0
    finally:
        os.close(fd)


def test_ejecutar_sin_pass_fds_no_hereda(tmp_path):
    archivo = tmp_path / "dato"
    archivo.write_bytes(b"x")
    fd = os.open(archivo, os.O_RDONLY)
    try:
        codigo, _salida, _error = lector_rar._ejecutar(
            ["/bin/sh", "-c", f"test -e /proc/self/fd/{fd}"], home=tmp_path,
            timeout=5, tope_salida=1024, pass_fds=())
        assert codigo != 0
    finally:
        os.close(fd)
