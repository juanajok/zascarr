"""Transporte aislado de la petición v4; no conectado a UI ni al auxiliar.

Envía una línea ya construida por el socket Unix configurado y valida una
respuesta v4 de esquema cerrado. No inicia unidades ni ejecuta scripts; no
registra la petición, el testigo ni la firma. `aceptada` solo significa
admisión, no actualización terminada. Un fallo después de abrir el socket es
`incierto`: pudo enviarse algo y perderse la respuesta.
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
    "aceptada", "esquema_invalido", "firma_invalida", "caducada",
    "autorizacion_invalida", "repetida", "operacion_en_curso", "no_disponible",
    "incierta",
})


class CodigoTransporteV4(StrEnum):
    ACEPTADA = "aceptada"
    RECHAZADA = "rechazada"
    OCUPADA = "ocupada"
    NO_DISPONIBLE = "no_disponible"
    RESPUESTA_INVALIDA = "respuesta_invalida"
    INCIERTO = "incierto"
    INCIERTA = "incierta"


class IntercambioInciertoError(Exception):
    """La conexión se estableció: pudo enviarse algo y perderse la respuesta."""


Conversar = Callable[[str, bytes], Awaitable[bytes]]


async def _conversar(ruta: str, peticion: bytes) -> bytes:
    lector, escritor = await asyncio.open_unix_connection(ruta, limit=MAX_RESPUESTA * 2)
    try:
        try:
            escritor.write(peticion)
            await escritor.drain()
            return await lector.readuntil(b"\n")
        except BaseException as exc:
            raise IntercambioInciertoError from exc
    finally:
        escritor.close()
        with contextlib.suppress(OSError):
            await escritor.wait_closed()


async def pedir_actualizacion_v4(
    settings: Settings,
    peticion: bytes,
    *,
    id_: str,
    conversar: Conversar = _conversar,
) -> CodigoTransporteV4:
    """Envía y valida; timeout o fallo tras conectar es incierto."""
    if type(peticion) is not bytes or not 0 < len(peticion) <= MAX_PETICION:
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if not isinstance(id_, str) or not _ID.fullmatch(id_):
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    socket_file = getattr(settings, "ops4_socket_file", None)
    if not isinstance(socket_file, str) or not socket_file:
        return CodigoTransporteV4.NO_DISPONIBLE
    try:
        respuesta = await asyncio.wait_for(
            conversar(socket_file, peticion), timeout=TIEMPO_S
        )
    except (IntercambioInciertoError, TimeoutError):
        return CodigoTransporteV4.INCIERTO
    except Exception:  # noqa: BLE001 — conexión no establecida o fallo previo
        return CodigoTransporteV4.NO_DISPONIBLE
    return _interpretar(respuesta, id_)


def _sin_duplicados(pares: list[tuple[str, object]]) -> dict[str, object]:
    claves = [clave for clave, _ in pares]
    if len(claves) != len(set(claves)):
        raise ValueError("clave duplicada")
    return dict(pares)


def _interpretar(respuesta: object, id_: object) -> CodigoTransporteV4:
    if type(respuesta) is not bytes or len(respuesta) > MAX_RESPUESTA:
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if (
        not respuesta.endswith(b"\n")
        or respuesta.count(b"\n") != 1
        or respuesta.endswith(b"\r\n")
    ):
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    try:
        cuerpo = json.loads(
            respuesta[:-1].decode("utf-8"), object_pairs_hook=_sin_duplicados
        )
    except (UnicodeDecodeError, ValueError, RecursionError):
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if not isinstance(cuerpo, dict) or set(cuerpo) != _CAMPOS_RESPUESTA:
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if type(cuerpo["v"]) is not int or cuerpo["v"] != 4:
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if not isinstance(id_, str) or not _ID.fullmatch(id_) or cuerpo["id"] != id_:
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    resultado = cuerpo["resultado"]
    if not isinstance(resultado, str) or resultado not in ("aceptada", "rechazada", "incierta"):
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if not isinstance(cuerpo["codigo"], str) or cuerpo["codigo"] not in _CODIGOS:
        return CodigoTransporteV4.RESPUESTA_INVALIDA
    if resultado == "aceptada" and cuerpo["codigo"] == "aceptada":
        return CodigoTransporteV4.ACEPTADA
    if resultado == "rechazada" and cuerpo["codigo"] == "operacion_en_curso":
        return CodigoTransporteV4.OCUPADA
    if resultado == "rechazada" and cuerpo["codigo"] not in ("aceptada", "incierta"):
        return CodigoTransporteV4.RECHAZADA
    if resultado == "incierta" and cuerpo["codigo"] == "incierta":
        return CodigoTransporteV4.INCIERTA
    return CodigoTransporteV4.RESPUESTA_INVALIDA
