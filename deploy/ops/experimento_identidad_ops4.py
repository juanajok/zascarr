"""Experimento aislado de coherencia textual; no autoriza ninguna operación.

No realiza E/S ni comprueba la autenticidad, existencia o procedencia de los
commits, la seguridad del snapshot ni que el avance sea fast-forward. La marca
«fiable» es una afirmación del llamador, no una verificación. No conectar este
resultado a un autorizador o ejecutor de despliegue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Resultado(Enum):
    """Resultado exclusivamente descriptivo de la comparación."""

    COHERENTE = "coherente"
    RECHAZADO = "rechazado"
    REQUIERE_DECISION = "requiere_decision"


@dataclass(frozen=True)
class Identidad:
    """SHA y declaración explícita de fiabilidad suministrados por el llamador."""

    sha: object = None
    fiable: object = False


_SHA = re.compile(r"[0-9a-f]{40}\Z")


def comparar_identidades(
    aprobado: object = None,
    ref_reconfirmada: object = None,
    snapshot: object = None,
    head0: object = None,
) -> Resultado:
    """Comparar SHA-1 completos en minúsculas, sin normalizar las entradas.

    Las cuatro identidades deben declararse fiables explícitamente y coincidir
    exactamente aprobado, ref y snapshot. HEAD0 debe ser distinto: si coincide,
    el no-op no está soportado y requiere una decisión externa. Cualquier dato
    ausente, inválido o no fiable se rechaza antes de considerar el no-op.
    COHERENTE no significa autorización ni implica verificaciones adicionales.
    """
    identidades = (aprobado, ref_reconfirmada, snapshot, head0)
    if any(
        type(item) is not Identidad
        or item.fiable is not True
        or type(item.sha) is not str
        or _SHA.fullmatch(item.sha) is None
        for item in identidades
    ):
        return Resultado.RECHAZADO

    if aprobado.sha != ref_reconfirmada.sha or aprobado.sha != snapshot.sha:
        return Resultado.RECHAZADO
    if aprobado.sha == head0.sha:
        return Resultado.REQUIERE_DECISION
    return Resultado.COHERENTE
