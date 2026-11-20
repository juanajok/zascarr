"""Contrato app→host de autorización corta; sin socket, unidad ni efectos."""
from __future__ import annotations

import concurrent.futures
import hashlib
import hmac
import json
import threading

import pytest

from deploy.ops.verificador_autorizacion_ops4 import (
    DOMINIO,
    CodigoAutorizacion,
    verificar_autorizacion,
)
from zascarr.services.autorizacion_actualizacion import crear_autorizacion

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000


def token(**cambios):
    datos = {"clave": CLAVE, "id_": ID, "ahora": AHORA, "ttl": 60}
    datos.update(cambios)
    return crear_autorizacion(**datos)


def firmar(cuerpo: dict) -> bytes:
    bruto = json.dumps(cuerpo, separators=(",", ":")).encode()
    return bruto + b"." + hmac.new(CLAVE, DOMINIO + bruto, hashlib.sha256).hexdigest().encode()


def test_acepta_una_vez_y_rechaza_repeticion() -> None:
    usados: set[str] = set()

    def reclamar(id_: str) -> bool:
        if id_ in usados:
            return False
        usados.add(id_)
        return True

    valor = token()
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoAutorizacion.ACEPTADA
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
    ) is CodigoAutorizacion.REPETIDA
    assert usados == {ID}


def test_limites_de_ventana_y_tolerancia() -> None:
    def acepta(_: str) -> bool:
        return True

    valor = token()
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA - 120, reclamar_uso=acepta,
    ) is CodigoAutorizacion.ACEPTADA
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA + 60, reclamar_uso=acepta,
    ) is CodigoAutorizacion.ACEPTADA
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA + 61, reclamar_uso=acepta,
    ) is CodigoAutorizacion.CADUCADA
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA - 121, reclamar_uso=acepta,
    ) is CodigoAutorizacion.INVALIDA


@pytest.mark.parametrize("cambio", [
    {"clave": b"corta"}, {"clave": b"x" * 33}, {"clave": "x" * 32},
    {"id_": "A" * 32}, {"id_": "a" * 31}, {"id_": "../" + "a" * 29},
    {"ahora": True}, {"ahora": -1}, {"ahora": 2**63},
    {"ttl": 0}, {"ttl": 301}, {"ttl": True},
])
def test_emisor_rechaza_parametros_invalidos(cambio) -> None:
    with pytest.raises(ValueError):
        token(**cambio)


def test_token_no_contiene_contrasena_ni_hash() -> None:
    valor = token()
    assert b"prueba" not in valor.lower()
    assert b"password" not in valor.lower()
    assert b"pbkdf2" not in valor.lower()
    assert len(valor) <= 2048


@pytest.mark.parametrize("valor", [
    b"", b".", b"solo-cuerpo", b"a.b.c", b"x" * 2049,
    token() + b"\r", token() + b"\n", token().replace(b'"v":1', b'"v":2'),
])
def test_formas_y_firmas_invalidas(valor) -> None:
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) in (CodigoAutorizacion.INVALIDA, CodigoAutorizacion.CADUCADA)


@pytest.mark.parametrize("cuerpo", [
    {"v": 1, "accion": "otra", "id": ID, "creada": AHORA, "expira": AHORA + 60},
    {"v": True, "accion": "actualizar", "id": ID, "creada": AHORA, "expira": AHORA + 60},
    {"v": 1, "accion": "actualizar", "id": ID, "creada": True, "expira": AHORA + 60},
    {"v": 1, "accion": "actualizar", "id": ID, "creada": AHORA, "expira": AHORA + 301},
    {"v": 1, "accion": "actualizar", "id": ID, "creada": AHORA, "expira": 2**63},
    {"v": 1, "accion": "actualizar", "id": ID, "creada": -1, "expira": AHORA + 60},
    {"v": 1, "accion": "actualizar", "id": ID, "creada": AHORA, "expira": AHORA + 60, "extra": 1},
    {"v": 1, "accion": "actualizar", "id": "A" * 32, "creada": AHORA, "expira": AHORA + 60},
])
def test_campos_estrictos(cuerpo: dict) -> None:
    assert verificar_autorizacion(
        firmar(cuerpo), clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoAutorizacion.INVALIDA


def test_claves_duplicadas_rechazadas() -> None:
    cuerpo = (
        b'{"v":1,"v":1,"accion":"actualizar","id":"' + ID.encode()
        + b'","creada":1800000000,"expira":1800000060}'
    )
    firma = hmac.new(CLAVE, DOMINIO + cuerpo, hashlib.sha256).hexdigest().encode()
    assert verificar_autorizacion(
        cuerpo + b"." + firma, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoAutorizacion.INVALIDA


def test_callback_que_falla_o_no_devuelve_true_deniega() -> None:
    def revienta(_id: str) -> bool:
        raise RuntimeError("fallo de persistencia")

    valor = token()
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=revienta,
    ) is CodigoAutorizacion.NO_DISPONIBLE
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: 1,
    ) is CodigoAutorizacion.REPETIDA


def test_id_esperado_liga_el_testigo_a_la_peticion() -> None:
    consumos: list[str] = []

    def reclamar(id_: str) -> bool:
        consumos.append(id_)
        return True

    valor = token()
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar, id_esperado="b" * 32,
    ) is CodigoAutorizacion.INVALIDA
    assert consumos == []
    assert verificar_autorizacion(
        valor, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar, id_esperado=ID,
    ) is CodigoAutorizacion.ACEPTADA
    assert consumos == [ID]


def test_otra_clave_y_cuerpo_no_objeto_se_rechazan() -> None:
    assert verificar_autorizacion(
        token(), clave=b"z" * 32, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoAutorizacion.INVALIDA
    cuerpo = b"[]"
    firma = hmac.new(CLAVE, DOMINIO + cuerpo, hashlib.sha256).hexdigest().encode()
    assert verificar_autorizacion(
        cuerpo + b"." + firma, clave=CLAVE, ahora=AHORA, reclamar_uso=lambda _: True,
    ) is CodigoAutorizacion.INVALIDA


def test_token_invalido_no_llama_al_callback() -> None:
    consumos: list[str] = []
    assert verificar_autorizacion(
        token() + b"x", clave=CLAVE, ahora=AHORA,
        reclamar_uso=lambda i: consumos.append(i) or True,
    ) is CodigoAutorizacion.INVALIDA
    assert verificar_autorizacion(
        token(), clave=b"z" * 32, ahora=AHORA,
        reclamar_uso=lambda i: consumos.append(i) or True,
    ) is CodigoAutorizacion.INVALIDA
    assert consumos == []


def test_clave_o_reloj_invalidos_no_consumen() -> None:
    consumos = []
    assert verificar_autorizacion(
        token(), clave=b"x" * 31, ahora=AHORA, reclamar_uso=lambda i: consumos.append(i) or True,
    ) is CodigoAutorizacion.NO_DISPONIBLE
    assert verificar_autorizacion(
        token(), clave=CLAVE, ahora=True, reclamar_uso=lambda i: consumos.append(i) or True,
    ) is CodigoAutorizacion.NO_DISPONIBLE
    assert consumos == []


def test_hilos_solo_un_consumo() -> None:
    usados: set[str] = set()
    cerrojo = threading.Lock()

    def reclamar(id_: str) -> bool:
        with cerrojo:
            if id_ in usados:
                return False
            usados.add(id_)
            return True

    valor = token()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(
            lambda _: verificar_autorizacion(
                valor, clave=CLAVE, ahora=AHORA, reclamar_uso=reclamar,
            ), range(32),
        ))
    assert resultados.count(CodigoAutorizacion.ACEPTADA) == 1
    assert resultados.count(CodigoAutorizacion.REPETIDA) == 31
