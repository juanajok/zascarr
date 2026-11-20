"""Pruebas del lector fijo de credenciales; nunca ejecuta Docker."""
from __future__ import annotations

import hashlib
import subprocess

import pytest

from deploy.ops.lector_credenciales_ops4 import (
    DOCKER_FIJO,
    PATH_FIJO,
    LectorCredenciales,
)
from deploy.ops.prueba_viva_ops4 import verificar_prueba_viva

SAL = b"sal"
ITER = 10_000
HASH = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
    "sha256", b"clave", SAL, ITER
).hex()


class Ejecutor:
    def __init__(self, returncode: int = 0, stdout: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.llamadas: list[tuple[list[str], dict]] = []

    def __call__(self, argv, **kwargs):
        self.llamadas.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, b"")


def test_orden_fija_y_salida_valida() -> None:
    ejecutor = Ejecutor(stdout=b"password|" + HASH.encode() + b"\n")
    lector = LectorCredenciales(ejecutor)
    assert lector.leer() == ("password", HASH)
    argv, kwargs = ejecutor.llamadas[0]
    assert argv[:4] == [DOCKER_FIJO, "exec", "zascarr-db", "psql"]
    assert "--env-file" not in argv
    assert kwargs["env"] == {"PATH": PATH_FIJO, "DOCKER_CONFIG": "/run/zascarr-ops/docker"}
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["check"] is False
    assert kwargs["timeout"] == 8


def test_composicion_con_verificador() -> None:
    lector = LectorCredenciales(Ejecutor(stdout=b"password|" + HASH.encode()))
    assert verificar_prueba_viva("clave", lector.leer) is True
    assert verificar_prueba_viva("otra", lector.leer) is False


@pytest.mark.parametrize("resultado", [
    Ejecutor(returncode=1, stdout=b"password|" + HASH.encode()),
    Ejecutor(stdout=b""),
    Ejecutor(stdout=b"sin-separador"),
    Ejecutor(stdout=b"password|\n"),
    Ejecutor(stdout=b"password|hash\nsegunda"),
    Ejecutor(stdout=b"password|" + b"x" * 5000),
])
def test_fallos_y_formas_invalidas(resultado: Ejecutor) -> None:
    assert LectorCredenciales(resultado).leer() is None


def test_excepcion_del_ejecutor() -> None:
    def revienta(*_args, **_kwargs):
        raise OSError("docker caído")

    assert LectorCredenciales(revienta).leer() is None


@pytest.mark.parametrize("usuario,base", [
    ("", "zascarr"), ("a b", "zascarr"), ("x;DROP", "zascarr"),
    ("comics_admin", "zascarr;DROP"), ("a" * 65, "zascarr"),
])
def test_identidad_invalida(usuario: str, base: str) -> None:
    with pytest.raises(ValueError):
        LectorCredenciales(Ejecutor(), db_user=usuario, db_name=base)
