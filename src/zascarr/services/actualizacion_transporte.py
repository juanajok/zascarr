"""Transporte aislado de la petición v3 de actualización; no hay ruta de UI.

Envía una línea ya preparada por el socket Unix configurado y valida una
respuesta JSON de esquema cerrado. No inicia unidades, no ejecuta scripts y no
está importado por routers ni por `main`. No registra la petición, la
contraseña ni la firma. Una respuesta `aceptada` solo significa que el
auxiliar admitió la solicitud, no que la actualización haya terminado.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import re
from collections.abc import Awaitable, Callable
from enum import StrEnum

from zascarr.config import Settings

MAX_PETICION = 4096
MAX_RESPUESTA = 4096
TIEMPO_S = 20.0
_CAMPOS_RESPUESTA = frozenset({"v", "id", "resultado", "codigo"})
_ID = re.compile(r"[0-9a-f]{32}\Z")
_CODIGOS = frozenset({
    "aceptada", "esquema_invalido", "firma_invalida", "caducada", "repetida",
    "prueba_invalida", "no_disponible",
})


class CodigoTransporte(StrEnum):
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    NO_DISPONIBLE = "no_disponible"
    RESPUESTA_INVALIDA = "respuesta_invalida"


Conversar = Callable[[str, bytes], Awaitable[bytes]]


async def _conversar(ruta: str, peticion: bytes) -> bytes:
    lector, escritor = await asyncio.open_unix_connection(ruta, limit=MAX_RESPUESTA * 2)
    try:
        escritor.write(peticion)
        await escritor.drain()
        return await lector.readuntil(b"\n")
    finally:
        escritor.close()
        with contextlib.suppress(OSError):
            await escritor.wait_closed()


async def pedir_actualizacion(
    settings: Settings,
    peticion: bytes,
    *,
    id_: str,
    conversar: Conversar = _conversar,
) -> CodigoTransporte:
    """Envía y valida; cualquier fallo se traduce en NO_DISPONIBLE."""
    if not isinstance(peticion, bytes) or not 0 < len(peticion) <= MAX_PETICION:
        return CodigoTransporte.RESPUESTA_INVALIDA
    if not isinstance(id_, str) or not _ID.fullmatch(id_):
        return CodigoTransporte.RESPUESTA_INVALIDA
    try:
        respuesta = await asyncio.wait_for(
            conversar(settings.ops_socket_file, peticion), timeout=TIEMPO_S
        )
    except Exception:  # noqa: BLE001 — un fallo de transporte no autoriza nada
        return CodigoTransporte.NO_DISPONIBLE
    return _interpretar(respuesta, id_)


def _sin_duplicados(pares: list[tuple[str, object]]) -> dict[str, object]:
    claves = [clave for clave, _ in pares]
    if len(claves) != len(set(claves)):
        raise ValueError("clave duplicada")
    return dict(pares)


def _interpretar(respuesta: object, id_: object) -> CodigoTransporte:
    if not isinstance(respuesta, bytes) or len(respuesta) > MAX_RESPUESTA:
        return CodigoTransporte.RESPUESTA_INVALIDA
    if not respuesta.endswith(b"\n") or respuesta.count(b"\n") != 1:
        return CodigoTransporte.RESPUESTA_INVALIDA
    try:
        cuerpo = json.loads(
            respuesta[:-1].decode("utf-8"), object_pairs_hook=_sin_duplicados
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        return CodigoTransporte.RESPUESTA_INVALIDA
    if not isinstance(cuerpo, dict) or set(cuerpo) != _CAMPOS_RESPUESTA:
        return CodigoTransporte.RESPUESTA_INVALIDA
    if type(cuerpo["v"]) is not int or cuerpo["v"] != 3:
        return CodigoTransporte.RESPUESTA_INVALIDA
    if not isinstance(id_, str) or not _ID.fullmatch(id_) or cuerpo["id"] != id_:
        return CodigoTransporte.RESPUESTA_INVALIDA
    resultado = cuerpo["resultado"]
    if not isinstance(resultado, str) or resultado not in ("aceptada", "rechazada"):
        return CodigoTransporte.RESPUESTA_INVALIDA
    if not isinstance(cuerpo["codigo"], str) or cuerpo["codigo"] not in _CODIGOS:
        return CodigoTransporte.RESPUESTA_INVALIDA
    if resultado == "aceptada" and cuerpo["codigo"] == "aceptada":
        return CodigoTransporte.ACEPTADA
    if resultado == "rechazada" and cuerpo["codigo"] != "aceptada":
        return CodigoTransporte.RECHAZADA
    return CodigoTransporte.RESPUESTA_INVALIDA
