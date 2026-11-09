# ruff: noqa: E501
"""
Reautenticación — BL-OPS3 (#456): comprobar la contraseña ACTUAL antes de un cambio de seguridad.

Un servicio compartido (también lo usará «Restaurar…», BL-OPS2) con dos defensas distintas:

- el **retraso progresivo** es el contador GLOBAL de la cuenta que ya usa `/login`
  (`services/auth.intentar_credenciales`): los fallos de aquí lo alimentan y los de `/login`, también;
- un **bloqueo duro propio**: al `UMBRAL_FALLOS`.º fallo en `VENTANA_S`, se rechaza todo durante
  `BLOQUEO_S` desde el último fallo, **sin calcular PBKDF2** ni anotar nada. Solo vale para esta
  comprobación: bloquearla no impide entrar por `/login` ni al revés.

El estado vive en memoria (un solo proceso, CLAUDE.md §4): un reinicio lo pone a cero. Las constantes
están aquí, una sola vez, como parámetros del servicio.
"""
from __future__ import annotations

import enum
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from zascarr.config import Settings
from zascarr.services.auth import ColaDeVerificacionLlenaError, intentar_credenciales

#: Fallos seguidos (dentro de `VENTANA_S`) tras los cuales se bloquea la comprobación.
UMBRAL_FALLOS = 5
#: Los fallos caducan a los 15 minutos (los mismos que el retraso progresivo de `/login`).
VENTANA_S = 15 * 60
#: Cuánto dura el bloqueo, contado desde el ÚLTIMO fallo. Decisión del PO (Q-2): 30 minutos.
BLOQUEO_S = 30 * 60


class Reauth(enum.StrEnum):
    OK = "ok"
    INCORRECTA = "incorrecta"
    BLOQUEADA = "bloqueada"
    OCUPADA = "ocupada"


@dataclass(frozen=True)
class ResultadoReauth:
    resultado: Reauth
    #: Solo con `BLOQUEADA`: hora (epoch) en que termina el bloqueo, para poder decirla.
    hasta_epoch: float | None = None


_cerrojo = threading.Lock()
_fallos: list[float] = []          # instantes de los fallos que siguen dentro de la ventana
_bloqueada_hasta = 0.0


def reiniciar_estado() -> None:
    """Pone a cero los fallos y el bloqueo (estado de módulo; lo usan los tests)."""
    global _bloqueada_hasta
    with _cerrojo:
        _fallos.clear()
        _bloqueada_hasta = 0.0


def _anotar_fallo(ahora: float) -> None:
    global _bloqueada_hasta
    with _cerrojo:
        _fallos[:] = [t for t in _fallos if ahora - t <= VENTANA_S]
        _fallos.append(ahora)
        if len(_fallos) >= UMBRAL_FALLOS:
            _bloqueada_hasta = ahora + BLOQUEO_S


def _acierto() -> None:
    global _bloqueada_hasta
    with _cerrojo:
        _fallos.clear()
        _bloqueada_hasta = 0.0


async def comprobar_contrasena_actual(
    password: str, settings: Settings, *, reloj: Callable[[], float] = time.time,
) -> ResultadoReauth:
    """¿Es `password` la contraseña con la que se entra hoy?

    El bloqueo se mira ANTES de entrar en la cola de verificaciones (de 3): en una ráfaga pueden colarse
    como mucho 2 intentos de más. Un acierto pone el contador a cero; la cola llena (`OCUPADA`) no cuenta
    como fallo. Ni la contraseña ni su hash se registran."""
    ahora = reloj()
    with _cerrojo:
        hasta = _bloqueada_hasta
    if hasta > ahora:
        return ResultadoReauth(Reauth.BLOQUEADA, hasta)
    try:
        ok = await intentar_credenciales(settings.auth_username, password, settings)
    except ColaDeVerificacionLlenaError:
        return ResultadoReauth(Reauth.OCUPADA)
    if ok:
        _acierto()
        return ResultadoReauth(Reauth.OK)
    _anotar_fallo(reloj())
    return ResultadoReauth(Reauth.INCORRECTA)
