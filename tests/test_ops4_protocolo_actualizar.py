"""Contrato v3 aislado: no autoriza ni inicia operaciones."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from deploy.ops import zascarr_ops as auxiliar

CLAVE = bytes(range(32))


def peticion(**cambios):
    datos = {"v": 3, "id": "a" * 32, "accion": "actualizar", "creada": 1800000000,
             "prueba": "clave|ñ\ncon comillas \"", "firma": "0" * 64}
    datos.update(cambios)
    return datos


def linea(datos):
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"


def test_firma_canonica_y_protocolo_aislado():
    datos = peticion()
    datos["firma"] = protocolo.firmar(CLAVE, datos)
    mensaje = b'zascarr-ops/actualizar/v3\x00' + json.dumps(
        [3, datos["id"], "actualizar", 1800000000, datos["prueba"]],
        ensure_ascii=False, separators=(",", ":"),
    ).encode()
    assert datos["firma"] == hmac.new(CLAVE, mensaje, hashlib.sha256).hexdigest()
    recibido = protocolo.parsear(linea(datos))
    assert recibido == datos
    assert protocolo.verificar_firma(CLAVE, recibido)
    # El auxiliar real no reconoce la versión ni siquiera firmada correctamente.
    assert auxiliar.parsear(linea(datos)) is None
    assert "actualizar" not in auxiliar.UNIDADES


@pytest.mark.parametrize("campo,valor", [
    ("id", "b" * 32), ("creada", 1800000001), ("prueba", "otra"),
])
def test_modificar_campo_firmado_invalida_firma(campo, valor):
    datos = peticion()
    datos["firma"] = protocolo.firmar(CLAVE, datos)
    datos[campo] = valor
    assert not protocolo.verificar_firma(CLAVE, datos)
    assert not protocolo.verificar_firma(b"x" * 32, datos)


@pytest.mark.parametrize("cambios", [
    {"v": True}, {"v": 2}, {"id": "A" * 32}, {"id": "a" * 31},
    {"accion": "restaurar"}, {"accion": "actualizar "},
    {"creada": True}, {"creada": -1}, {"creada": 2**63}, {"creada": 1.0},
    {"prueba": ""}, {"prueba": "ñ" * 257}, {"prueba": "\ud800"},
    {"firma": "F" * 64}, {"firma": "0" * 63}, {"extra": "x"},
])
def test_esquema_cerrado(cambios):
    datos = peticion(**cambios)
    # ensure_ascii permite probar el sustituto aislado sin codificarlo en UTF-8.
    bruto = json.dumps(datos, ensure_ascii=True).encode() + b"\n"
    assert protocolo.parsear(bruto) is None
    assert not protocolo.verificar_firma(CLAVE, datos)


def test_falta_campo_y_limites_de_prueba():
    datos = peticion(prueba="ñ" * 256)
    assert protocolo.parsear(linea(datos)) == datos
    del datos["prueba"]
    assert protocolo.parsear(linea(datos)) is None
    with pytest.raises(ValueError, match="esquema"):
        protocolo.firmar(CLAVE, datos)


@pytest.mark.parametrize("bruto", [
    b"", b"{}", b"{}\n\n", b"\xff\n", b"[]\n", b"{mal}\n",
    b'{"v":3,"v":3}\n', b"x" * 4096 + b"\n",
])
def test_encuadre_y_json_invalidos(bruto):
    assert protocolo.parsear(bruto) is None


def test_duplicado_en_objeto_por_lo_demas_valido():
    datos = peticion()
    bruto = linea(datos).replace(b'{"v":3,', b'{"v":3,"v":3,')
    assert protocolo.parsear(bruto) is None


def test_clave_y_firma_invalidas():
    datos = peticion()
    with pytest.raises(ValueError, match="clave"):
        protocolo.firmar(b"corta", datos)
    assert not protocolo.verificar_firma(b"corta", datos)
    assert not protocolo.verificar_firma(CLAVE, datos)


def test_vector_hmac_fijo():
    datos = peticion(prueba="clave")
    assert protocolo.firmar(CLAVE, datos) == (
        "a932ea053eb2ea7c7c73a4c03c2a3e3c45aa0243c7bfd42d784ddbd41b78c4a3"
    )


def test_limite_exacto_de_linea():
    base = linea(peticion())
    relleno = b" " * (protocolo.MAX_LINEA - len(base))
    ajustada = base[:-1] + relleno + b"\n"
    assert len(ajustada) == protocolo.MAX_LINEA
    assert protocolo.parsear(ajustada) is not None
    assert protocolo.parsear(ajustada[:-1] + b" \n") is None


def test_repetir_validacion_no_es_proteccion_replay():
    datos = peticion()
    datos["firma"] = protocolo.firmar(CLAVE, datos)
    assert protocolo.verificar_firma(CLAVE, protocolo.parsear(linea(datos)))
    assert protocolo.verificar_firma(CLAVE, protocolo.parsear(linea(datos)))


def test_crlf_no_se_acepta():
    datos = peticion()
    datos["firma"] = protocolo.firmar(CLAVE, datos)
    bruto = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode() + b"\r\n"
    assert protocolo.parsear(bruto) is None
