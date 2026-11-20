"""Pruebas de la composición de admisión; sin socket, BD ni systemd."""
from __future__ import annotations

import hashlib
import json

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from deploy.ops.admision_actualizar_ops4 import CodigoAdmision
from deploy.ops.admision_host_actualizar_ops4 import admitir_host

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000
SAL = b"sal-host"
HASH = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
    "sha256", b"clave", SAL, 10_000
).hex()


def construir(*, prueba: str = "clave", id_: str = ID) -> bytes:
    datos = {"v": 3, "id": id_, "accion": "actualizar", "creada": AHORA,
             "prueba": prueba, "firma": "0" * 64}
    datos["firma"] = protocolo.firmar(CLAVE, datos)
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


class Lector:
    def __init__(self, datos=None, *, falla: bool = False) -> None:
        self.datos = datos if datos is not None else ("password", HASH)
        self.falla = falla
        self.llamadas = 0

    def leer(self):
        self.llamadas += 1
        if self.falla:
            raise RuntimeError("BD caída / secreto")
        return self.datos


def admitir(linea, lector, *, reclama=True, clave=CLAVE):
    return admitir_host(
        linea, clave=clave, ahora=AHORA, lector=lector,
        reclamar_id=lambda _: reclama,
    )


def test_composicion_correcta() -> None:
    lector = Lector()
    assert admitir(construir(), lector) is CodigoAdmision.ACEPTADA
    assert lector.llamadas == 1


@pytest.mark.parametrize("datos", [
    ("password", HASH), ("user_password", HASH),
])
def test_modos_validos(datos) -> None:
    assert admitir(construir(), Lector(datos)) is CodigoAdmision.ACEPTADA


@pytest.mark.parametrize("datos", [
    ("none", HASH), ("otro", HASH), ("password", ""), ("password", "malformado"),
])
def test_credenciales_no_validas(datos) -> None:
    assert admitir(construir(), Lector(datos)) is CodigoAdmision.PRUEBA_INVALIDA


def test_password_incorrecta() -> None:
    assert admitir(construir(prueba="otra"), Lector()) is CodigoAdmision.PRUEBA_INVALIDA


def test_bd_caida_falla_cerrado() -> None:
    # La composición no distingue "BD caída" de "contraseña incorrecta":
    # ambas deniegan, sin filtrar la causa ni conceder la operación.
    assert admitir(construir(), Lector(falla=True)) is CodigoAdmision.PRUEBA_INVALIDA


def test_lector_sin_leer_falla_cerrado() -> None:
    assert admitir(construir(), object()) is CodigoAdmision.NO_DISPONIBLE


def test_firma_o_replay_no_consulta_bd() -> None:
    lector = Lector()
    assert admitir(construir(), lector, clave=b"x" * 32) is CodigoAdmision.FIRMA_INVALIDA
    assert lector.llamadas == 0
    assert admitir(construir(), lector, reclama=False) is CodigoAdmision.REPETIDA
    assert lector.llamadas == 0


def test_no_expone_secretos_en_resultado() -> None:
    lector = Lector(falla=True)
    resultado = admitir(construir(prueba="secreto"), lector)
    assert resultado is CodigoAdmision.PRUEBA_INVALIDA
    assert "secreto" not in str(resultado)
