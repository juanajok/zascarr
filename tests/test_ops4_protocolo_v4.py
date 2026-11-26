"""Contrato v4 app→host; sin socket, unidad, BD ni ejecución."""
from __future__ import annotations

import json

import pytest

from deploy.ops import protocolo_actualizar_v4_ops4 as protocolo
from zascarr.services.autorizacion_actualizacion import crear_autorizacion
from zascarr.services.ops_actualizacion_v4 import construir_peticion_v4

CLAVE = bytes(range(32))
ID = "a" * 32
ID_OTRO = "b" * 32
AHORA = 1_800_000_000


def crear_testigo(id_: str = ID) -> bytes:
    return crear_autorizacion(clave=CLAVE, id_=id_, ahora=AHORA, ttl=60)


def peticion(*, id_: str = ID, creada: int = AHORA, token: bytes | None = None) -> bytes:
    return construir_peticion_v4(
        CLAVE, id=id_, creada=creada,
        autorizacion=crear_testigo() if token is None else token,
    )


def test_paridad_y_esquema_sin_contrasena() -> None:
    linea = peticion()
    objeto = protocolo.parsear(linea)
    assert objeto is not None
    assert objeto["v"] == 4
    assert set(objeto) == {"v", "id", "accion", "creada", "autorizacion", "firma"}
    assert b"prueba" not in linea and b"password" not in linea and b"pbkdf2" not in linea
    assert protocolo.verificar_firma(CLAVE, objeto)
    assert protocolo.decodificar_autorizacion(objeto["autorizacion"]) == crear_testigo()


@pytest.mark.parametrize("linea", [
    b"", b"{}\n", b"x" * 4097, b'{"v":3}\n',
    peticion()[:-1] + b"\r\n", peticion() + b"\n",
])
def test_encuadre_y_esquema_invalidos(linea: bytes) -> None:
    assert protocolo.parsear(linea) is None


def test_firma_de_peticion_incorrecta_no_valida() -> None:
    objeto = protocolo.parsear(peticion())
    assert objeto is not None
    objeto["firma"] = "0" * 64
    assert protocolo.verificar_firma(CLAVE, objeto) is False


def test_constructor_rechaza_parametros_invalidos() -> None:
    for cambio in (
        {"id": "A" * 32}, {"id": "a" * 31},
        {"creada": True}, {"creada": -1}, {"creada": 2**63},
    ):
        datos = {"id": ID, "creada": AHORA, "autorizacion": crear_testigo()}
        datos.update(cambio)
        with pytest.raises(ValueError):
            construir_peticion_v4(CLAVE, **datos)


def test_constructor_rechaza_autorizacion_invalida() -> None:
    for token in (b"", b"x" * 2049, "texto", bytearray(b"x")):
        with pytest.raises(ValueError):
            construir_peticion_v4(CLAVE, id=ID, creada=AHORA, autorizacion=token)


def test_autorizacion_no_canonica_se_rechaza() -> None:
    objeto = protocolo.parsear(peticion())
    assert objeto is not None
    assert protocolo.decodificar_autorizacion(objeto["autorizacion"] + "=") is None


def test_v4_no_acepta_v3_ni_campos_extra() -> None:
    v3 = {
        "v": 3, "id": ID, "accion": "actualizar", "creada": AHORA,
        "prueba": "clave", "firma": "0" * 64,
    }
    assert protocolo.parsear(
        json.dumps(v3, separators=(",", ":")).encode() + b"\n",
    ) is None
    objeto = protocolo.parsear(peticion())
    assert objeto is not None
    objeto["extra"] = 1
    assert protocolo.parsear(
        json.dumps(objeto, separators=(",", ":")).encode() + b"\n",
    ) is None
