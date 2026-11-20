"""Pruebas del formato canónico A; sin ficheros, root ni emisión."""
from __future__ import annotations

import pytest

from deploy.ops.experimento_registro_aprobacion_ops4 import (
    MAX_BYTES,
    Registro,
    RegistroInvalidoError,
    deserializar,
    serializar,
    vigente,
)

REGISTRO = Registro(
    sha="a" * 40, head0="b" * 40, instalacion="instalacion",
    origen="origin/main", huella_p="c" * 64, nonce="nonce", emitida=1_800_000_000,
)


def test_ida_y_vuelta_canonica() -> None:
    datos = serializar(REGISTRO)
    assert datos.endswith(b"\n")
    assert deserializar(datos) == REGISTRO


@pytest.mark.parametrize("datos", [
    b'{"v":1,"v":1}\n',
    b'{"v":1}\n',
    (b'{"v":1,"sha":"' + b"a" * 40 + b'","head0":"' + b"b" * 40
     + b'","instalacion":"i","origen":"origin/main","huella_p":"' + b"c" * 64
     + b'","nonce":"n","emitida":1,"extra":1}\n'),
    b'{"emitida":1,"v":1}\n',
    b'no-json\n',
    b'{"v":1}\n{"v":1}\n',
    b'{"v":1}\r\n',
    b"x" * (MAX_BYTES + 1),
])
def test_entradas_invalidas(datos: bytes) -> None:
    with pytest.raises(RegistroInvalidoError):
        deserializar(datos)


def test_no_canonico_se_rechaza() -> None:
    datos = serializar(REGISTRO)
    with pytest.raises(RegistroInvalidoError):
        deserializar(datos.replace(b'"v":1', b'"v": 1'))


@pytest.mark.parametrize("campo,valor", [
    ("sha", "a" * 39), ("head0", "A" * 40), ("huella_p", "c" * 63),
    ("instalacion", " "), ("origen", "main"), ("nonce", ""), ("emitida", True),
])
def test_validacion_de_campos(campo: str, valor: object) -> None:
    with pytest.raises(RegistroInvalidoError):
        serializar(Registro(**({**REGISTRO.__dict__, campo: valor})))


def test_vigencia_estricta() -> None:
    inicio = REGISTRO.emitida
    assert vigente(REGISTRO, inicio)
    assert vigente(REGISTRO, inicio + 24 * 3600 - 1)
    assert not vigente(REGISTRO, inicio - 1)
    assert not vigente(REGISTRO, inicio + 24 * 3600)
    with pytest.raises(RegistroInvalidoError):
        vigente(REGISTRO, True)
