"""Pruebas del constructor aislado, sin conectar al auxiliar."""
from __future__ import annotations

import json

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from deploy.ops import zascarr_ops as auxiliar
from zascarr.services.ops_actualizacion_protocolo import construir_peticion

CLAVE = bytes(range(32))
ID = "a" * 32


def construir(**cambios):
    parametros = {"clave": CLAVE, "id": ID, "creada": 1800000000, "prueba": "clave"}
    parametros.update(cambios)
    return construir_peticion(**parametros)


def test_vector_fijo_y_paridad_con_verificador():
    linea = construir()
    datos = protocolo.parsear(linea)
    assert datos is not None
    assert datos == {"v": 3, "id": ID, "accion": "actualizar", "creada": 1800000000,
                     "prueba": "clave", "firma":
                     "a932ea053eb2ea7c7c73a4c03c2a3e3c45aa0243c7bfd42d784ddbd41b78c4a3"}
    assert protocolo.verificar_firma(CLAVE, datos)
    assert auxiliar.parsear(linea) is None
    assert "actualizar" not in auxiliar.UNIDADES


@pytest.mark.parametrize("prueba", ["ñ\n\"\\\x00", "ñ" * 256, "\x00" * 512, "e\u0301", "é"])
def test_utf8_controles_y_limites(prueba):
    linea = construir(prueba=prueba)
    assert len(linea) <= 4096
    assert linea.count(b"\n") == 1 and linea.endswith(b"\n")
    datos = protocolo.parsear(linea)
    assert datos is not None and datos["prueba"] == prueba
    assert protocolo.verificar_firma(CLAVE, datos)


@pytest.mark.parametrize("campo,valor", [
    ("clave", b""), ("clave", b"x" * 31), ("clave", bytearray(32)),
    ("id", "A" * 32), ("id", "a" * 31), ("id", None),
    ("creada", True), ("creada", -1), ("creada", 2**63), ("creada", 1.0),
    ("prueba", ""), ("prueba", "ñ" * 257), ("prueba", "\ud800"), ("prueba", b"x"),
])
def test_rechaza_datos_invalidos_sin_exponer_secretos(campo, valor, capsys):
    with pytest.raises(ValueError) as error:
        construir(**{campo: valor})
    assert "ñ" not in str(error.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("creada", [0, 2**63 - 1])
def test_extremos_instante(creada):
    datos = protocolo.parsear(construir(creada=creada))
    assert datos is not None and protocolo.verificar_firma(CLAVE, datos)


@pytest.mark.parametrize("campo,valor", [
    ("id", "b" * 32), ("creada", 1800000001), ("prueba", "otra"),
    ("firma", "0" * 64),
])
def test_integridad(campo, valor):
    datos = json.loads(construir())
    datos[campo] = valor
    assert not protocolo.verificar_firma(CLAVE, datos)
    assert not protocolo.verificar_firma(b"x" * 32, json.loads(construir()))
