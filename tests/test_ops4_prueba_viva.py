"""Pruebas de la verificación PBKDF2 aislada; sin BD, Docker ni red."""
from __future__ import annotations

import hashlib

import pytest

from deploy.ops import prueba_viva_ops4 as verificador
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


@pytest.mark.parametrize("stored", [
    "pbkdf2_sha256$10000$$" + "11" * 32,
    "pbkdf2_sha256$10000$" + "aa" * 65 + "$" + "11" * 32,
    "pbkdf2_sha256$10000$aa$" + "11" * 31,
    "pbkdf2_sha256$10000$aa$" + "11" * 33,
    "pbkdf2_sha256$9999$aa$" + "11" * 32,
    "pbkdf2_sha256$2000001$aa$" + "11" * 32,
    "pbkdf2_sha256$no$aa$" + "11" * 32,
    "pbkdf2_sha256$10000$zz$" + "11" * 32,
    "md5$10000$aa$" + "11" * 32,
    "x" * (verificador.MAX_HASH_CHARS + 1),
])
def test_hash_imposible_no_calcula_pbkdf2(stored: str, monkeypatch) -> None:
    def prohibido(*_args, **_kwargs):
        raise AssertionError("un hash inválido no debe consumir PBKDF2")

    monkeypatch.setattr(verificador.hashlib, "pbkdf2_hmac", prohibido)
    assert comprobar_hash("clave", stored) is False


@pytest.mark.parametrize("iterations", [10_000, 600_000, 2_000_000])
def test_limites_de_iteraciones_admitidos_sin_calcular_coste_maximo(
    iterations: int, monkeypatch,
) -> None:
    calls = []
    digest = bytes.fromhex("11" * 32)

    def compute(*args):
        calls.append(args)
        return digest

    monkeypatch.setattr(verificador.hashlib, "pbkdf2_hmac", compute)
    stored = f"pbkdf2_sha256${iterations}$aa${digest.hex()}"
    assert comprobar_hash("clave", stored) is True
    assert calls == [("sha256", b"clave", b"\xaa", iterations)]


@pytest.mark.parametrize("length", [256, 257])
def test_limite_hash_con_formato_que_de_otro_modo_seria_valido(length: int, monkeypatch) -> None:
    digest = bytes.fromhex("11" * 32)
    base = f"pbkdf2_sha256$10000$aa${digest.hex()}"
    # int() admite espacios: sin el límite, ambas formas llegarían a PBKDF2.
    padding = " " * (length - len(base))
    stored = f"pbkdf2_sha256${padding}10000$aa${digest.hex()}"
    assert len(stored) == length
    calls = []

    def compute(*args):
        calls.append(args)
        return digest

    monkeypatch.setattr(verificador.hashlib, "pbkdf2_hmac", compute)
    assert comprobar_hash("clave", stored) is (length <= verificador.MAX_HASH_CHARS)
    assert len(calls) == (1 if length <= verificador.MAX_HASH_CHARS else 0)


def test_sal_maxima_admitida_con_pbkdf2_real() -> None:
    salt = b"s" * verificador.MAX_SAL_BYTES
    digest = hashlib.pbkdf2_hmac("sha256", b"clave", salt, ITERACIONES)
    stored = f"pbkdf2_sha256${ITERACIONES}${salt.hex()}${digest.hex()}"
    assert comprobar_hash("clave", stored) is True


def test_compatibilidad_real_con_hash_actual_de_la_app() -> None:
    from zascarr.services.auth import hash_password

    stored = hash_password("clave-sintetica-actual")
    _algorithm, iterations, salt, digest = stored.split("$")
    assert int(iterations) == 600_000
    assert len(bytes.fromhex(salt)) == 16
    assert len(bytes.fromhex(digest)) == verificador.DIGEST_BYTES
    assert comprobar_hash("clave-sintetica-actual", stored) is True
    assert comprobar_hash("incorrecta", stored) is False
