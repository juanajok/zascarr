"""Transporte v4 aislado; sin socket real, UI ni auxiliar."""
from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

from deploy.ops.registro_repeticiones_ops4 import (
    abrir_directorio_autorizaciones,
    crear_reclamador_durable,
)
from tests._host_v4 import CodigoV4, admitir_v4
from zascarr.services.actualizacion_transporte_v4 import (
    CodigoTransporteV4,
    IntercambioInciertoError,
    _conversar,
    pedir_actualizacion_v4,
)

ID = "a" * 32
SETTINGS = SimpleNamespace(ops4_socket_file="/no/existe.sock")


def respuesta_v4(codigo: CodigoV4) -> bytes:
    resultado = "aceptada" if codigo is CodigoV4.ACEPTADA else "rechazada"
    return json.dumps(
        {"v": 4, "id": ID, "resultado": resultado, "codigo": codigo.value},
        separators=(",", ":"),
    ).encode() + b"\n"


def respuesta(**cambios) -> bytes:
    datos = {"v": 4, "id": ID, "resultado": "aceptada", "codigo": "aceptada"}
    datos.update(cambios)
    return json.dumps(datos, separators=(",", ":")).encode() + b"\n"


def conversar(respuesta_: bytes):
    async def fake(_ruta: str, _peticion: bytes) -> bytes:
        return respuesta_
    return fake


@pytest.mark.asyncio
async def test_aceptada_y_rechazada() -> None:
    assert await pedir_actualizacion_v4(
        SETTINGS, b"peticion\n", id_=ID, conversar=conversar(respuesta()),
    ) is CodigoTransporteV4.ACEPTADA
    assert await pedir_actualizacion_v4(
        SETTINGS, b"peticion\n", id_=ID,
        conversar=conversar(respuesta(resultado="rechazada", codigo="repetida")),
    ) is CodigoTransporteV4.RECHAZADA
    assert await pedir_actualizacion_v4(
        SETTINGS, b"peticion\n", id_=ID,
        conversar=conversar(respuesta(
            resultado="rechazada", codigo="operacion_en_curso",
        )),
    ) is CodigoTransporteV4.OCUPADA


@pytest.mark.asyncio
@pytest.mark.parametrize("valor", [
    b"", b"x" * 4097, bytearray(b"x"), b"{}\n", b"x\n",
    respuesta(v=3), respuesta(id="b" * 32), respuesta(resultado="otra"),
    respuesta(codigo="codigo_inventado"),
    respuesta(resultado="aceptada", codigo="repetida"),
    respuesta(resultado="rechazada", codigo="aceptada"),
    respuesta()[:-1] + b"\r\n", respuesta() + b"\n",
    b'{"v":4,"v":4,"id":"' + ID.encode() + b'","resultado":"aceptada","codigo":"aceptada"}\n',
])
async def test_respuestas_invalidas_no_son_exito(valor) -> None:
    assert await pedir_actualizacion_v4(
        SETTINGS, b"peticion\n", id_=ID, conversar=conversar(valor),
    ) is CodigoTransporteV4.RESPUESTA_INVALIDA


@pytest.mark.asyncio
async def test_timeout_y_fallo_tras_conectar_son_inciertos() -> None:
    async def timeout(_ruta, _peticion):
        raise TimeoutError

    async def incierto(_ruta, _peticion):
        raise IntercambioInciertoError

    for fake in (timeout, incierto):
        assert await pedir_actualizacion_v4(
            SETTINGS, b"peticion\n", id_=ID, conversar=fake,
        ) is CodigoTransporteV4.INCIERTO


@pytest.mark.asyncio
async def test_fallo_antes_de_conectar_es_no_disponible() -> None:
    async def falla(_ruta, _peticion):
        raise OSError("socket no disponible")

    assert await pedir_actualizacion_v4(
        SETTINGS, b"peticion\n", id_=ID, conversar=falla,
    ) is CodigoTransporteV4.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_peticion_o_id_invalidos_no_conversan() -> None:
    llamadas = []

    async def fake(ruta, peticion):
        llamadas.append((ruta, peticion))
        return respuesta()

    assert await pedir_actualizacion_v4(
        SETTINGS, b"", id_=ID, conversar=fake,
    ) is CodigoTransporteV4.RESPUESTA_INVALIDA
    assert await pedir_actualizacion_v4(
        SETTINGS, b"x" * 4097, id_=ID, conversar=fake,
    ) is CodigoTransporteV4.RESPUESTA_INVALIDA
    assert await pedir_actualizacion_v4(
        SETTINGS, b"x", id_="no-id", conversar=fake,
    ) is CodigoTransporteV4.RESPUESTA_INVALIDA
    assert llamadas == []


@pytest.mark.asyncio
async def test_conversador_real_por_socket_temporal(tmp_path) -> None:
    ruta = tmp_path / "ops.sock"

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            linea = await reader.readline()
            assert linea == b"peticion\n"
            writer.write(respuesta())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handler, path=str(ruta))
    async with server:
        assert await pedir_actualizacion_v4(
            SimpleNamespace(ops4_socket_file=str(ruta)), b"peticion\n", id_=ID,
            conversar=_conversar,
        ) is CodigoTransporteV4.ACEPTADA


@pytest.mark.asyncio
async def test_flujo_v4_socket_temporal_con_consumo_durable(tmp_path) -> None:
    from zascarr.services.autorizacion_actualizacion import crear_autorizacion
    from zascarr.services.ops_actualizacion_v4 import construir_peticion_v4

    clave = bytes(range(32))
    ahora = 1_800_000_000
    token = crear_autorizacion(clave=clave, id_=ID, ahora=ahora, ttl=60)
    peticion = construir_peticion_v4(clave, id=ID, creada=ahora, autorizacion=token)
    ruta = tmp_path / "ops.sock"
    directorio = tmp_path / "autorizaciones"
    directorio.mkdir(mode=0o700)
    directorio.chmod(0o700)
    fd = abrir_directorio_autorizaciones(directorio, uid_esperado=os.getuid())
    try:
        reclamar = crear_reclamador_durable(fd)

        async def handler(reader, writer):
            try:
                linea = await reader.readline()
                codigo = admitir_v4(
                    linea, clave=clave, ahora=ahora, reclamar_uso=reclamar,
                )
                writer.write(respuesta_v4(codigo))
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_unix_server(handler, path=str(ruta))
        async with server:
            config = SimpleNamespace(ops4_socket_file=str(ruta))
            assert await pedir_actualizacion_v4(
                config, peticion, id_=ID,
            ) is CodigoTransporteV4.ACEPTADA
            assert await pedir_actualizacion_v4(
                config, peticion, id_=ID,
            ) is CodigoTransporteV4.RECHAZADA
    finally:
        os.close(fd)


@pytest.mark.asyncio
async def test_sin_socket_v4_no_cae_al_de_copias() -> None:
    settings = SimpleNamespace(ops_socket_file="/tmp/copias.sock")
    assert await pedir_actualizacion_v4(
        settings, b"peticion\n", id_=ID,
        conversar=lambda *_: pytest.fail("no debe abrir el socket de copias"),
    ) is CodigoTransporteV4.NO_DISPONIBLE
