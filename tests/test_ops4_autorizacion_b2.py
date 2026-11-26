"""B2a: la verificación del testigo no consume; el consumo es un paso aparte."""
from __future__ import annotations

from deploy.ops.verificador_autorizacion_ops4 import (
    CodigoAutorizacion,
    verificar_autorizacion,
    verificar_testigo_sin_consumo,
)
from zascarr.services.autorizacion_actualizacion import crear_autorizacion

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000


def _token(id_: str = ID, ahora: int = AHORA, ttl: int = 60) -> bytes:
    return crear_autorizacion(clave=CLAVE, id_=id_, ahora=ahora, ttl=ttl)


def test_verificar_sin_consumo_acepta_sin_marcas() -> None:
    assert verificar_testigo_sin_consumo(
        _token(), clave=CLAVE, ahora=AHORA, id_esperado=ID,
    ) is CodigoAutorizacion.ACEPTADA


def test_verificar_sin_consumo_rechaza_firma_ventana_e_id() -> None:
    token = _token()
    roto = token[:-1] + (b"0" if token[-1:] != b"0" else b"1")
    assert verificar_testigo_sin_consumo(
        roto, clave=CLAVE, ahora=AHORA, id_esperado=ID,
    ) is CodigoAutorizacion.INVALIDA
    assert verificar_testigo_sin_consumo(
        _token(ahora=AHORA - 61), clave=CLAVE, ahora=AHORA, id_esperado=ID,
    ) is CodigoAutorizacion.CADUCADA
    assert verificar_testigo_sin_consumo(
        _token(), clave=CLAVE, ahora=AHORA, id_esperado="b" * 32,
    ) is CodigoAutorizacion.INVALIDA


def test_verificar_autorizacion_conserva_el_consumo_unico() -> None:
    llamadas: list[str] = []

    def reclamar(id_: str) -> bool:
        llamadas.append(id_)
        return id_ not in llamadas[:-1]

    assert verificar_autorizacion(
        _token(), clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
        id_esperado=ID,
    ) is CodigoAutorizacion.ACEPTADA
    assert verificar_autorizacion(
        _token(), clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
        id_esperado=ID,
    ) is CodigoAutorizacion.REPETIDA
    assert llamadas == [ID, ID]


def test_verificar_autorizacion_no_consume_si_falla_la_firma() -> None:
    llamadas: list[str] = []
    token = _token()
    roto = token[:-1] + (b"0" if token[-1:] != b"0" else b"1")
    assert verificar_autorizacion(
        roto, clave=CLAVE, ahora=AHORA,
        reclamar_uso=lambda id_: llamadas.append(id_) or True,
        id_esperado=ID,
    ) is CodigoAutorizacion.INVALIDA
    assert llamadas == []
