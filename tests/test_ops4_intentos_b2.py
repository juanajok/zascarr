"""B2a: marca de intento durable y exclusiva (no es el consumo)."""
from __future__ import annotations

import os
import stat

import pytest

from deploy.ops.registro_repeticiones_ops4 import (
    RegistroNoDisponibleError,
    abrir_directorio_intentos,
    reclamar_intento,
)

ID = "a" * 32


def _directorio(tmp_path):
    ruta = tmp_path / "intentos"
    ruta.mkdir(mode=0o700)
    return ruta


def test_marca_exclusiva_y_0600(tmp_path) -> None:
    ruta = _directorio(tmp_path)
    fd = abrir_directorio_intentos(ruta, uid_esperado=os.getuid())
    try:
        assert reclamar_intento(ID, directorio_fd=fd) is True
        marca = ruta / ID
        assert marca.is_file()
        assert stat.S_IMODE(marca.stat().st_mode) == 0o600
        assert reclamar_intento(ID, directorio_fd=fd) is False
    finally:
        os.close(fd)


def test_directorio_no_seguro_falla_cerrado(tmp_path) -> None:
    ruta = tmp_path / "intentos"
    ruta.mkdir()
    os.chmod(ruta, 0o755)
    with pytest.raises(RegistroNoDisponibleError):
        abrir_directorio_intentos(ruta, uid_esperado=os.getuid())


def test_propietario_esperado_distinto_falla_cerrado(tmp_path) -> None:
    ruta = _directorio(tmp_path)
    with pytest.raises(RegistroNoDisponibleError):
        abrir_directorio_intentos(ruta, uid_esperado=os.getuid() + 1)


def test_fallo_de_sincronizacion_no_acredita_la_marca(tmp_path) -> None:
    ruta = _directorio(tmp_path)
    fd = abrir_directorio_intentos(ruta, uid_esperado=os.getuid())
    try:
        with pytest.raises(RegistroNoDisponibleError):
            reclamar_intento(
                ID, directorio_fd=fd,
                sincronizar=lambda _fd: (_ for _ in ()).throw(OSError("fsync")),
            )
    finally:
        os.close(fd)


def test_id_invalido_no_crea_marca(tmp_path) -> None:
    ruta = _directorio(tmp_path)
    fd = abrir_directorio_intentos(ruta, uid_esperado=os.getuid())
    try:
        with pytest.raises(RegistroNoDisponibleError):
            reclamar_intento("../fuera", directorio_fd=fd)
    finally:
        os.close(fd)
    assert not (tmp_path / "fuera").exists()
