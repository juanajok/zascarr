"""Pruebas del transporte v3 con un conversador simulado; sin socket."""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from zascarr.services import actualizacion_transporte
from zascarr.services.actualizacion_transporte import (
    CodigoTransporte,
    pedir_actualizacion,
)

ID = "a" * 32
SETTINGS = SimpleNamespace(ops_socket_file="/run/zascarr-ops/ops.sock")


def respuesta(*, id_: str = ID, resultado: str = "aceptada", codigo: str = "aceptada",
              v: int = 3, extra: bool = False) -> bytes:
    cuerpo = {"v": v, "id": id_, "resultado": resultado, "codigo": codigo}
    if extra:
        cuerpo["texto"] = "secreto"
    return json.dumps(cuerpo, separators=(",", ":")).encode() + b"\n"


@pytest.mark.asyncio
async def test_aceptada_y_transporte_recibe_peticion() -> None:
    visto = {}

    async def conversar(ruta, peticion):
        visto["ruta"] = ruta
        visto["peticion"] = peticion
        return respuesta()

    resultado = await pedir_actualizacion(
        SETTINGS, b"peticion\n", id_=ID, conversar=conversar
    )
    assert resultado is CodigoTransporte.ACEPTADA
    assert visto == {"ruta": "/run/zascarr-ops/ops.sock", "peticion": b"peticion\n"}


@pytest.mark.asyncio
@pytest.mark.parametrize("resultado", [
    ("rechazada", "caducada"), ("rechazada", "prueba_invalida"),
    ("rechazada", "no_disponible"),
])
async def test_rechazos_validos(resultado) -> None:
    async def conversar(_ruta, _peticion):
        return respuesta(resultado=resultado[0], codigo=resultado[1])

    assert await pedir_actualizacion(
        SETTINGS, b"peticion\n", id_=ID, conversar=conversar
    ) is CodigoTransporte.RECHAZADA


@pytest.mark.asyncio
@pytest.mark.parametrize("bruto", [
    b"", b"{}\n", b"{}\n\n", respuesta(id_="b" * 32), respuesta(v=2),
    respuesta(extra=True), respuesta(resultado="otra"), respuesta(codigo="otro"),
    respuesta(resultado="rechazada", codigo="aceptada"), b"x" * 5000,
])
async def test_respuestas_invalidas(bruto: bytes) -> None:
    async def conversar(_ruta, _peticion):
        return bruto

    assert await pedir_actualizacion(
        SETTINGS, b"peticion\n", id_=ID, conversar=conversar
    ) is CodigoTransporte.RESPUESTA_INVALIDA


@pytest.mark.asyncio
async def test_fallo_de_transporte_no_autoriza() -> None:
    async def revienta(_ruta, _peticion):
        raise OSError("socket caído")

    assert await pedir_actualizacion(
        SETTINGS, b"peticion\n", id_=ID, conversar=revienta
    ) is CodigoTransporte.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_peticion_invalida_no_llama_al_transporte() -> None:
    llamadas = []

    async def conversar(_ruta, _peticion):
        llamadas.append(1)
        return respuesta()

    assert await pedir_actualizacion(
        SETTINGS, b"", id_=ID, conversar=conversar
    ) is CodigoTransporte.RESPUESTA_INVALIDA
    assert llamadas == []


@pytest.mark.asyncio
async def test_timeout_no_autoriza(monkeypatch) -> None:
    monkeypatch.setattr(actualizacion_transporte, "TIEMPO_S", 0.01)

    async def tarda(_ruta, _peticion):
        await asyncio.sleep(1)
        return respuesta()

    assert await pedir_actualizacion(
        SETTINGS, b"peticion\n", id_=ID, conversar=tarda
    ) is CodigoTransporte.NO_DISPONIBLE
