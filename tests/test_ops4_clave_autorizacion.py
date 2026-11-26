"""Pruebas del lector de clave dedicada; sin red, web ni instalación."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from zascarr.services.clave_autorizacion import leer_clave_autorizacion

CLAVE = bytes(range(32))
HEX = CLAVE.hex().encode()
UID = os.getuid()


def escribir(tmp_path: Path, datos: bytes, modo: int = 0o440, uid: int | None = None) -> Path:
    path = tmp_path / "autorizacion.key"
    path.write_bytes(datos)
    path.chmod(modo)
    if uid is not None and uid != os.getuid():
        pytest.skip("cambiar propietario requiere privilegios")
    return path


@pytest.mark.parametrize("datos", [HEX, HEX + b"\n"])
def test_formato_del_instalador(tmp_path: Path, datos: bytes) -> None:
    path = escribir(tmp_path, datos)
    assert leer_clave_autorizacion(path, uid_esperado=UID) == CLAVE


@pytest.mark.parametrize("datos", [
    b"", b"00", HEX + b"\r\n", HEX + b"\n\n", b"z" * 64,
    b"00" * 31, b"00" * 33, HEX + b"\nX",
])
def test_tamano_o_forma_invalida(tmp_path: Path, datos: bytes) -> None:
    path = escribir(tmp_path, datos)
    with pytest.raises(ValueError) as error:
        leer_clave_autorizacion(path, uid_esperado=UID)
    assert str(error.value) == "clave no disponible"


@pytest.mark.parametrize("modo", [0o400, 0o440])
def test_modos_permitidos(tmp_path: Path, modo: int) -> None:
    path = escribir(tmp_path, HEX, modo=modo)
    assert leer_clave_autorizacion(
        path, uid_esperado=UID, modo_esperado=modo,
    ) == CLAVE


@pytest.mark.parametrize("modo", [0o420, 0o444, 0o640, 0o600])
def test_modo_no_previsto_deniega(tmp_path: Path, modo: int) -> None:
    path = escribir(tmp_path, HEX, modo=modo)
    with pytest.raises(ValueError):
        leer_clave_autorizacion(path, uid_esperado=UID, modo_esperado=0o440)


def test_propietario_incorrecto_deniega(tmp_path: Path) -> None:
    path = escribir(tmp_path, HEX)
    otro = UID + 1 if UID < 2**32 - 1 else UID - 1
    with pytest.raises(ValueError):
        leer_clave_autorizacion(path, uid_esperado=otro)


def test_enlace_simbolico_deniega(tmp_path: Path) -> None:
    real = escribir(tmp_path, HEX)
    enlace = tmp_path / "enlace.key"
    enlace.symlink_to(real)
    with pytest.raises(ValueError):
        leer_clave_autorizacion(enlace, uid_esperado=UID)


def test_fifo_deniega_sin_bloquear(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo.key"
    os.mkfifo(fifo)
    fifo.chmod(0o440)
    with pytest.raises(ValueError):
        leer_clave_autorizacion(fifo, uid_esperado=UID)


def test_directorio_deniega(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        leer_clave_autorizacion(tmp_path, uid_esperado=UID)


@pytest.mark.parametrize("uid", [True, -1, 2**32, "0"])
def test_uid_invalido_deniega(uid) -> None:
    with pytest.raises(ValueError):
        leer_clave_autorizacion("/dev/null", uid_esperado=uid)


@pytest.mark.parametrize("modo", [True, 0o600, 0o444, "440"])
def test_modo_invalido_deniega(modo) -> None:
    with pytest.raises(ValueError):
        leer_clave_autorizacion("/dev/null", uid_esperado=UID, modo_esperado=modo)


def test_fichero_inexistente_deniega(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        leer_clave_autorizacion(tmp_path / "no-existe", uid_esperado=UID)
