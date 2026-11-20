"""Pruebas de la verificación PBKDF2 aislada; sin BD, Docker ni red."""
from __future__ import annotations

import hashlib

import pytest

from deploy.ops.prueba_viva_ops4 import comprobar_hash, verificar_prueba_viva

ITERACIONES = 10_000
SAL = b"sal-de-prueba"
HASH = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
    "sha256", b"clave", SAL, ITERACIONES
).hex()


@pytest.mark.parametrize("modo", ["password", "user_password"])
def test_modos_validos_y_hash_correcto(modo: str) -> None:
    assert verificar_prueba_viva("clave", lambda: (modo, HASH)) is True


@pytest.mark.parametrize("prueba", ["otra", "", "ñ" * 257, None, b"clave"])
def test_prueba_incorrecta_o_invalida(prueba: object) -> None:
    assert verificar_prueba_viva(prueba, lambda: ("password", HASH)) is False


@pytest.mark.parametrize("modo", ["none", "", "otro", None])
def test_modo_no_valido_falla_cerrado(modo: object) -> None:
    assert verificar_prueba_viva("clave", lambda: (modo, HASH)) is False


@pytest.mark.parametrize("hash_", [
    "", "pbkdf2_sha256$10000$" + SAL.hex() + "$",
    "pbkdf2_sha256$1$" + SAL.hex() + "$00",
    "pbkdf2_sha256$2000001$" + SAL.hex() + "$00",
    "pbkdf2_sha256$10000$" + "$" + "00",
    "md5$10000$00$00", "pbkdf2_sha256$no$00$00",
    "pbkdf2_sha256$10000$zz$00", "pbkdf2_sha256$10000$00$zz",
])
def test_hash_malformado_falla_cerrado(hash_: str) -> None:
    assert comprobar_hash("clave", hash_) is False


def test_lector_que_falla_o_devuelve_forma_incorrecta() -> None:
    def revienta():
        raise RuntimeError("secreto de BD")

    assert verificar_prueba_viva("clave", revienta) is False
    assert verificar_prueba_viva("clave", lambda: None) is False
    assert verificar_prueba_viva("clave", lambda: ("password",)) is False
    assert verificar_prueba_viva("clave", lambda: ("password", HASH, "extra")) is False


def test_unicode_y_sal_no_vacia() -> None:
    hash_ = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
        "sha256", "contraseña".encode(), SAL, ITERACIONES
    ).hex()
    assert comprobar_hash("contraseña", hash_) is True
    assert comprobar_hash("contrasena", hash_) is False
