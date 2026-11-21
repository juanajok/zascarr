"""Contrato v4 app→host; sin socket, unidad, BD ni ejecución."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from deploy.ops import protocolo_actualizar_v4_ops4 as protocolo
from deploy.ops.admision_v4_actualizar_ops4 import CodigoV4, admitir_v4
from deploy.ops.registro_repeticiones_ops4 import (
    abrir_directorio_autorizaciones,
    crear_reclamador_durable,
)
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
        CLAVE, id=id_, creada=creada, autorizacion=crear_testigo() if token is None else token,
    )


def consumidor():
    usados: set[str] = set()
    llamadas: list[str] = []

    def reclamar(id_: str) -> bool:
        llamadas.append(id_)
        if id_ in usados:
            return False
        usados.add(id_)
        return True

    return reclamar, llamadas


def test_paridad_y_esquema_sin_contrasena() -> None:
    linea = peticion()
    objeto = protocolo.parsear(linea)
    assert objeto is not None
    assert objeto["v"] == 4
    assert set(objeto) == {"v", "id", "accion", "creada", "autorizacion", "firma"}
    assert b"prueba" not in linea and b"password" not in linea and b"pbkdf2" not in linea
    assert protocolo.verificar_firma(CLAVE, objeto)
    assert protocolo.decodificar_autorizacion(objeto["autorizacion"]) == crear_testigo()


def test_admite_una_vez_y_rechaza_repeticion() -> None:
    reclamar, llamadas = consumidor()
    linea = peticion()
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoV4.ACEPTADA
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoV4.REPETIDA
    assert llamadas == [ID, ID]


def test_id_de_testigo_debe_coincidir_con_la_peticion() -> None:
    reclamar, llamadas = consumidor()
    linea = construir_peticion_v4(
        CLAVE, id=ID, creada=AHORA, autorizacion=crear_testigo(ID_OTRO),
    )
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoV4.AUTORIZACION_INVALIDA
    assert llamadas == []


def test_caducidad_de_peticion_o_testigo_no_consume() -> None:
    reclamar, llamadas = consumidor()
    assert admitir_v4(
        peticion(creada=AHORA - 121), clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoV4.CADUCADA
    viejo = crear_autorizacion(clave=CLAVE, id_=ID, ahora=AHORA - 100, ttl=10)
    assert admitir_v4(
        peticion(token=viejo), clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoV4.CADUCADA
    assert llamadas == []


@pytest.mark.parametrize("linea", [
    b"", b"{}\n", b"x" * 4097, b"{\"v\":3}\n",
    peticion()[:-1] + b"\r\n", peticion() + b"\n",
])
def test_encuadre_y_esquema_invalidos(linea: bytes) -> None:
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoV4.ESQUEMA_INVALIDO


def test_firma_de_peticion_incorrecta_no_consume() -> None:
    objeto = protocolo.parsear(peticion())
    assert objeto is not None
    objeto["firma"] = "0" * 64
    linea = json.dumps(objeto, separators=(",", ":")).encode() + b"\n"
    llamadas = []
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA,
        reclamar_uso=lambda i: llamadas.append(i) or True,
    ) is CodigoV4.FIRMA_INVALIDA
    assert llamadas == []


def test_clave_o_reloj_invalidos_no_consumen() -> None:
    llamadas = []
    for clave, ahora in ((b"x" * 31, AHORA), (CLAVE, True), (CLAVE, -1)):
        assert admitir_v4(
            peticion(), clave=clave, ahora=ahora,
            reclamar_uso=lambda i: llamadas.append(i) or True,
        ) is CodigoV4.NO_DISPONIBLE
    assert llamadas == []


@pytest.mark.parametrize("cambio", [
    {"id": "A" * 32}, {"id": "a" * 31}, {"creada": True},
    {"creada": -1}, {"creada": 2**63},
])
def test_constructor_rechaza_parametros_invalidos(cambio) -> None:
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


def test_admision_no_acepta_v3_ni_campos_extra() -> None:
    v3 = {
        "v": 3, "id": ID, "accion": "actualizar", "creada": AHORA,
        "prueba": "clave", "firma": "0" * 64,
    }
    linea = json.dumps(v3, separators=(",", ":")).encode() + b"\n"
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoV4.ESQUEMA_INVALIDO
    objeto = protocolo.parsear(peticion())
    assert objeto is not None
    objeto["extra"] = 1
    linea = json.dumps(objeto, separators=(",", ":")).encode() + b"\n"
    assert admitir_v4(
        linea, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoV4.ESQUEMA_INVALIDO


def test_v4_con_consumo_durable_real(tmp_path: Path) -> None:
    directorio = tmp_path / "autorizaciones"
    directorio.mkdir(mode=0o700)
    directorio.chmod(0o700)
    fd = abrir_directorio_autorizaciones(directorio, uid_esperado=os.getuid())
    try:
        reclamar = crear_reclamador_durable(fd)
        linea = peticion()
        assert admitir_v4(
            linea, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
        ) is CodigoV4.ACEPTADA
        assert admitir_v4(
            linea, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
        ) is CodigoV4.REPETIDA
    finally:
        os.close(fd)
    assert (directorio / f"autorizacion-{ID}").exists()
