"""Transporte y admisión por un socket Unix temporal; sin host real ni ejecución."""
from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from deploy.ops.admision_actualizar_ops4 import CodigoAdmision
from deploy.ops.admision_host_actualizar_ops4 import admitir_host
from zascarr.services.actualizacion_transporte import (
    CodigoTransporte,
    pedir_actualizacion,
)
from zascarr.services.reautenticacion import Reauth, ResultadoReauth
from zascarr.services.solicitud_actualizacion import preparar_solicitud

CLAVE = bytes(range(32))
ID = "a" * 32
AHORA = 1_800_000_000
SAL = b"sal-socket"
HASH = "pbkdf2_sha256$10000$" + SAL.hex() + "$" + hashlib.pbkdf2_hmac(
    "sha256", b"clave", SAL, 10_000
).hex()


async def comprobar_ok(_p, _s):
    return ResultadoReauth(Reauth.OK)


def settings(tmp_path: Path, socket_path: Path) -> SimpleNamespace:
    clave = tmp_path / "ops.key"
    clave.write_text(CLAVE.hex() + "\n", encoding="ascii")
    return SimpleNamespace(
        auth_mode="password", ops_key_file=str(clave), ops_socket_file=str(socket_path)
    )


class Lector:
    def leer(self):
        return "password", HASH


def respuesta_para(linea: bytes, reclama) -> bytes:
    datos = protocolo.parsear(linea)
    assert datos is not None
    codigo = admitir_host(
        linea, clave=CLAVE, ahora=AHORA, lector=Lector(), reclamar_id=reclama,
    )
    if codigo is CodigoAdmision.ACEPTADA:
        resultado, code = "aceptada", "aceptada"
    else:
        resultado, code = "rechazada", "repetida"
    return json.dumps(
        {"v": 3, "id": datos["id"], "resultado": resultado, "codigo": code},
        separators=(",", ":"),
    ).encode() + b"\n"


@pytest.mark.asyncio
async def test_socket_temporal_admite_y_rechaza_repeticion(tmp_path: Path) -> None:
    socket_path = tmp_path / "ops.sock"
    reclamados: set[str] = set()

    def reclamar(id_: str) -> bool:
        if id_ in reclamados:
            return False
        reclamados.add(id_)
        return True

    async def handler(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            linea = await reader.readline()
            writer.write(respuesta_para(linea, reclamar))
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handler, path=str(socket_path))
    async with server:
        config = settings(tmp_path, socket_path)
        preparada = await preparar_solicitud(
            config, contrasena="clave", entiendo=True,
            ahora=AHORA, id_=ID, comprobar=comprobar_ok,
        )
        assert preparada.resultado.value == "preparada"
        primera = await pedir_actualizacion(
            config, preparada.linea.bytes(), id_=preparada.id
        )
        segunda = await pedir_actualizacion(
            config, preparada.linea.bytes(), id_=preparada.id
        )
    assert primera is CodigoTransporte.ACEPTADA
    assert segunda is CodigoTransporte.RECHAZADA
