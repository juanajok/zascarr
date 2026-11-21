"""Pruebas de la admisión aislada; no hay socket, unidad ni efectos."""
from __future__ import annotations

import json

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from deploy.ops.admision_actualizar_ops4 import (
    CodigoAdmision,
    admitir,
    admitir_con_reloj,
)

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000


def construir(*, creada: int = AHORA, id_: str = ID, prueba: str = "clave") -> bytes:
    datos = {"v": 3, "id": id_, "accion": "actualizar", "creada": creada,
             "prueba": prueba, "firma": "0" * 64}
    datos["firma"] = protocolo.firmar(CLAVE, datos)
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


class Dobles:
    def __init__(self, *, prueba: bool = True, reclama: bool = True) -> None:
        self.prueba = prueba
        self.reclama = reclama
        self.pruebas: list[str] = []
        self.ids: list[str] = []

    def verificar(self, prueba: str) -> bool:
        self.pruebas.append(prueba)
        return self.prueba

    def reclamar(self, id_: str) -> bool:
        self.ids.append(id_)
        return self.reclama


def test_acepta_solo_tras_firma_frescura_id_y_prueba() -> None:
    dobles = Dobles()
    resultado = admitir(
        construir(), clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    )
    assert resultado is CodigoAdmision.ACEPTADA
    assert dobles.ids == [ID]
    assert dobles.pruebas == ["clave"]


@pytest.mark.parametrize("linea,esperado", [
    (b"", CodigoAdmision.ESQUEMA_INVALIDO),
    (b"{}\n", CodigoAdmision.ESQUEMA_INVALIDO),
    (b"x" * 5000, CodigoAdmision.ESQUEMA_INVALIDO),
])
def test_esquema_invalido_no_llama_callbacks(linea: bytes, esperado) -> None:
    dobles = Dobles()
    assert admitir(
        linea, clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is esperado
    assert dobles.pruebas == [] and dobles.ids == []


def test_firma_incorrecta_no_reclama_ni_verifica() -> None:
    dobles = Dobles()
    assert admitir(
        construir(), clave=b"x" * 32, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is CodigoAdmision.FIRMA_INVALIDA
    assert dobles.pruebas == [] and dobles.ids == []


@pytest.mark.parametrize("creada", [AHORA - 121, AHORA + 121])
def test_frescura_fuera_de_tolerancia(creada: int) -> None:
    dobles = Dobles()
    assert admitir(
        construir(creada=creada), clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is CodigoAdmision.CADUCADA
    assert dobles.ids == []


@pytest.mark.parametrize("creada", [AHORA - 120, AHORA + 120])
def test_frescura_en_el_limite(creada: int) -> None:
    dobles = Dobles()
    assert admitir(
        construir(creada=creada), clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is CodigoAdmision.ACEPTADA


def test_repeticion_no_se_acepta_tras_autenticar() -> None:
    dobles = Dobles(reclama=False)
    assert admitir(
        construir(), clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is CodigoAdmision.REPETIDA
    assert dobles.pruebas == ["clave"]


def test_fallo_de_prueba_no_consume_reclamacion() -> None:
    dobles = Dobles(prueba=False)
    assert admitir(
        construir(), clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is CodigoAdmision.PRUEBA_INVALIDA
    assert dobles.ids == []


def test_prueba_incorrecta_se_rechaza() -> None:
    dobles = Dobles(prueba=False)
    assert admitir(
        construir(), clave=CLAVE, ahora=AHORA,
        verificar_prueba=dobles.verificar, reclamar_id=dobles.reclamar,
    ) is CodigoAdmision.PRUEBA_INVALIDA


def test_excepciones_de_callbacks_fallan_cerrado() -> None:
    def revienta(_: str) -> bool:
        raise RuntimeError("secreto /ruta")

    assert admitir(
        construir(), clave=CLAVE, ahora=AHORA,
        verificar_prueba=revienta, reclamar_id=lambda _: True,
    ) is CodigoAdmision.NO_DISPONIBLE
    assert admitir(
        construir(), clave=CLAVE, ahora=AHORA,
        verificar_prueba=lambda _: True, reclamar_id=revienta,
    ) is CodigoAdmision.NO_DISPONIBLE


@pytest.mark.parametrize("clave,ahora", [(b"x" * 31, AHORA), (CLAVE, True), (CLAVE, -1)])
def test_parametros_del_host_invalidos(clave, ahora) -> None:
    assert admitir(
        construir(), clave=clave, ahora=ahora,
        verificar_prueba=lambda _: True, reclamar_id=lambda _: True,
    ) is CodigoAdmision.NO_DISPONIBLE


def test_reloj_inyectado_e_invalido() -> None:
    assert admitir_con_reloj(
        construir(creada=AHORA), clave=CLAVE,
        verificar_prueba=lambda _: True, reclamar_id=lambda _: True,
        reloj=lambda: AHORA,
    ) is CodigoAdmision.ACEPTADA
    assert admitir_con_reloj(
        construir(creada=AHORA), clave=CLAVE,
        verificar_prueba=lambda _: True, reclamar_id=lambda _: True,
        reloj=lambda: True,
    ) is CodigoAdmision.NO_DISPONIBLE
    assert admitir_con_reloj(
        construir(creada=AHORA), clave=CLAVE,
        verificar_prueba=lambda _: True, reclamar_id=lambda _: True,
        reloj=lambda: (_ for _ in ()).throw(RuntimeError),
    ) is CodigoAdmision.NO_DISPONIBLE
