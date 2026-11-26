"""Regresiones de la marca de invocación del finalizador OPS4 (N2)."""
from __future__ import annotations

import os
import stat

import pytest

from deploy.ops import estado_actualizar_ops4 as finalizador
from deploy.ops import zascarr_actualizar_entrada as entrada

ID = "a" * 32
INVOCACION = "b" * 32


@pytest.fixture
def intentos(tmp_path, monkeypatch):
    ops4 = tmp_path / "ops4"
    ruta = ops4 / "intentos"
    ruta.mkdir(parents=True, mode=0o700)
    ruta.chmod(0o700)
    monkeypatch.setenv("ZASCARR_OPS4_DIR", str(ops4))
    monkeypatch.setenv("INVOCATION_ID", INVOCACION)
    return ruta


def test_rechaza_directorio_intentos_con_permisos_inseguros(intentos):
    intentos.chmod(0o755)
    with pytest.raises(ValueError):
        entrada._marcar_intento(ID)
    assert not (intentos / INVOCACION).exists()


def test_rechaza_directorio_intentos_enlace(tmp_path, intentos):
    real = tmp_path / "real"
    intentos.rename(real)
    intentos.symlink_to(real, target_is_directory=True)
    with pytest.raises(OSError):
        entrada._marcar_intento(ID)
    assert not (real / INVOCACION).exists()


def test_marca_escritura_parcial_y_fsync_de_fichero_y_directorio(intentos, monkeypatch):
    write_real = os.write
    fsync_real = os.fsync
    tipos = []

    def escribir_parcial(fd, datos):
        return write_real(fd, datos[:3])

    def registrar_fsync(fd):
        tipos.append(stat.S_IFMT(os.fstat(fd).st_mode))
        fsync_real(fd)

    monkeypatch.setattr(entrada.os, "write", escribir_parcial)
    monkeypatch.setattr(entrada.os, "fsync", registrar_fsync)
    entrada._marcar_intento(ID)
    marca = intentos / INVOCACION
    assert marca.read_bytes() == (ID + "\n").encode("ascii")
    assert stat.S_IMODE(marca.stat().st_mode) == 0o600
    assert tipos == [stat.S_IFREG, stat.S_IFDIR]


def test_finalizador_rechaza_enlace_fifo_y_marca_excesiva(tmp_path):
    marca = tmp_path / "marca"
    real = tmp_path / "real"
    real.write_text(ID + "\n", encoding="ascii")
    marca.symlink_to(real)
    assert finalizador._leer_intento(marca) is None
    marca.unlink()
    os.mkfifo(marca)
    assert finalizador._leer_intento(marca) is None
    marca.unlink()
    marca.write_text(ID + "\nX", encoding="ascii")
    assert finalizador._leer_intento(marca) is None
    assert finalizador._leer_intento(real) == ID
