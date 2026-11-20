"""Preparación aislada de una solicitud de actualización; no envía ni ejecuta.

Valida confirmación y contraseña, usa la reautenticación compartida y, solo si
todo pasa, construye la petición v3 firmada. No abre el socket del auxiliar,
no inicia unidades y no debe conectarse a la UI hasta completar autenticación
viva, antirreplay, estado durable y revisión de seguridad.

La contraseña nunca debe registrarse. El HMAC protege integridad, no
confidencialidad ni identidad.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import stat
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum

from zascarr.config import Settings
from zascarr.services.ops_actualizacion_protocolo import construir_peticion
from zascarr.services.reautenticacion import (
    Reauth,
    ResultadoReauth,
    comprobar_contrasena_actual,
)

MAX_PRUEBA_BYTES = 512


class ResultadoSolicitud(StrEnum):
    PREPARADA = "preparada"
    CONFIRMACION_REQUERIDA = "confirmacion_requerida"
    CONTRASENA_INVALIDA = "contrasena_invalida"
    AUTENTICACION_NO_ACTIVADA = "autenticacion_no_activada"
    NO_DISPONIBLE = "no_disponible"
    CONTRASENA_INCORRECTA = "contrasena_incorrecta"
    OCUPADA = "ocupada"
    BLOQUEADA = "bloqueada"


class PeticionFirmada:
    """Línea firmada opaca: contiene la contraseña; no debe registrarse ni copiarse."""

    __slots__ = ("_datos",)

    def __init__(self, datos: bytes) -> None:
        self._datos = datos

    def bytes(self) -> bytes:
        """Entrega los bytes para el futuro transporte; el llamador no debe registrarlos."""
        return self._datos

    def __repr__(self) -> str:
        return "<petición firmada redactada>"

    __str__ = __repr__


@dataclass(frozen=True)
class Preparacion:
    resultado: ResultadoSolicitud
    #: Contiene la contraseña firmada: nunca se muestra en `repr`; usar `.bytes()`.
    linea: PeticionFirmada | None = field(default=None, repr=False)
    id: str | None = None
    hasta_epoch: float | None = None


Comprobar = Callable[[str, Settings], Awaitable[ResultadoReauth]]


async def preparar_solicitud(
    settings: Settings,
    *,
    contrasena: object,
    entiendo: object,
    ahora: int | None = None,
    id_: str | None = None,
    comprobar: Comprobar = comprobar_contrasena_actual,
) -> Preparacion:
    """Devuelve una petición firmada solo tras confirmar y reautenticar.

    No envía la petición. Un fallo de validación no llama a la reautenticación;
    un resultado de reautenticación distinto de OK nunca construye la línea.
    """
    if entiendo is not True:
        return Preparacion(ResultadoSolicitud.CONFIRMACION_REQUERIDA)
    if not isinstance(contrasena, str):
        return Preparacion(ResultadoSolicitud.CONTRASENA_INVALIDA)
    try:
        if not 1 <= len(contrasena.encode("utf-8")) <= MAX_PRUEBA_BYTES:
            return Preparacion(ResultadoSolicitud.CONTRASENA_INVALIDA)
    except UnicodeEncodeError:
        return Preparacion(ResultadoSolicitud.CONTRASENA_INVALIDA)
    if settings.auth_mode == "none":
        return Preparacion(ResultadoSolicitud.AUTENTICACION_NO_ACTIVADA)
    if settings.auth_mode not in ("password", "user_password"):
        return Preparacion(ResultadoSolicitud.NO_DISPONIBLE)

    try:
        reauth = await comprobar(contrasena, settings)
    except Exception:  # noqa: BLE001 — un fallo de autenticación no debe abrir la solicitud
        return Preparacion(ResultadoSolicitud.NO_DISPONIBLE)
    if not isinstance(reauth, ResultadoReauth):
        return Preparacion(ResultadoSolicitud.NO_DISPONIBLE)
    if reauth.resultado is Reauth.INCORRECTA:
        return Preparacion(ResultadoSolicitud.CONTRASENA_INCORRECTA)
    if reauth.resultado is Reauth.OCUPADA:
        return Preparacion(ResultadoSolicitud.OCUPADA)
    if reauth.resultado is Reauth.BLOQUEADA:
        return Preparacion(ResultadoSolicitud.BLOQUEADA, hasta_epoch=reauth.hasta_epoch)
    if reauth.resultado is not Reauth.OK:
        return Preparacion(ResultadoSolicitud.NO_DISPONIBLE)

    identificador = id_ if id_ is not None else secrets.token_hex(16)
    instante = int(time.time()) if ahora is None else ahora
    try:
        clave = await asyncio.to_thread(_leer_clave, settings.ops_key_file)
        linea = construir_peticion(
            clave, id=identificador, creada=instante, prueba=contrasena
        )
    except (TypeError, ValueError):
        return Preparacion(ResultadoSolicitud.NO_DISPONIBLE)
    return Preparacion(
        ResultadoSolicitud.PREPARADA, linea=PeticionFirmada(linea), id=identificador
    )


def _leer_clave(ruta: object) -> bytes:
    """Lee una clave regular sin seguir enlaces; el instalador añade un LF final."""
    try:
        path = os.fspath(ruta)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except (OSError, TypeError, ValueError):
        raise ValueError("clave no disponible") from None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size not in (64, 65):
            raise ValueError("clave no disponible")
        datos = os.read(fd, 66)
    except OSError:
        raise ValueError("clave no disponible") from None
    finally:
        os.close(fd)
    if len(datos) == 65 and datos.endswith(b"\n"):
        datos = datos[:-1]
    if len(datos) != 64:
        raise ValueError("clave no disponible")
    try:
        clave = bytes.fromhex(datos.decode("ascii"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("clave no disponible") from None
    if len(clave) != 32:
        raise ValueError("clave no disponible")
    return clave
