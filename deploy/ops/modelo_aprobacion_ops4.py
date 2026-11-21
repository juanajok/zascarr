"""Modelo experimental y desconectado de la aprobación OPS4; no autoriza despliegues.

No resuelve persistencia ni durabilidad, bloqueo/concurrencia ni reloj fiable.
El llamador debe obtener y verificar esos controles externamente; este módulo no
comprueba remoto, operador, propiedad, procedencia ni integridad del registro.
Una transición devuelta no es durable y no permite ejecutar ninguna operación.
El mismo valor original puede bifurcarse; exclusión, CAS y anti-replay son externos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum


class Estado(Enum):
    AUTORIZADA = "autorizada"
    RESERVADA = "reservada"
    CONSUMIDA = "consumida"
    INCIERTA = "incierta"


class AprobacionInvalidaError(ValueError):
    """La aprobación o la transición no supera las guardas."""


def _identidad(value: object) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _sha(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def _utc(value: object) -> datetime:
    try:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise AprobacionInvalidaError("Fecha inválida")
        return value.astimezone(UTC)
    except (OverflowError, TypeError, ValueError) as exc:
        raise AprobacionInvalidaError("Fecha inválida") from exc


@dataclass(frozen=True)
class Aprobacion:
    """Datos abstractos, no una aprobación administrativa real ni persistida."""

    sha: str
    head_inicial: str
    instalacion: str
    origen: str
    huella_p: str
    nonce: str
    emitida: datetime
    estado: Estado = Estado.AUTORIZADA
    intento: str | None = None
    ultimo_instante: datetime | None = None

    def __post_init__(self) -> None:
        if not _sha(self.sha) or not _sha(self.head_inicial):
            raise AprobacionInvalidaError("SHA inválido")
        if not all(_identidad(x) for x in (
            self.instalacion, self.origen, self.huella_p, self.nonce
        )):
            raise AprobacionInvalidaError("Identidad inválida")
        emitida = _utc(self.emitida)
        if not isinstance(self.estado, Estado):
            raise AprobacionInvalidaError("Estado inválido")
        if (self.estado is Estado.AUTORIZADA and self.intento is not None) or (
            self.estado is not Estado.AUTORIZADA and not _identidad(self.intento)
        ):
            raise AprobacionInvalidaError("Intento incompatible con el estado")
        if self.estado is Estado.AUTORIZADA:
            if self.ultimo_instante is not None:
                raise AprobacionInvalidaError("Instante incompatible con el estado")
        else:
            ultimo = _utc(self.ultimo_instante)
            if ultimo < emitida or ultimo - emitida >= timedelta(hours=24):
                raise AprobacionInvalidaError("Instante de reserva inválido")


def _validar(a: Aprobacion, *, sha: str, head_inicial: str, instalacion: str,
             origen: str, huella_p: str, ahora: datetime, reloj_fiable: bool) -> None:
    if not isinstance(a, Aprobacion) or reloj_fiable is not True:
        raise AprobacionInvalidaError("Reloj o aprobación inválidos")
    instante = _utc(ahora)
    emitida = _utc(a.emitida)
    if not _sha(sha) or not _sha(head_inicial) or not all(
        _identidad(x) for x in (instalacion, origen, huella_p)
    ):
        raise AprobacionInvalidaError("Identidad inválida")
    if (sha, head_inicial, instalacion, origen, huella_p) != (
        a.sha, a.head_inicial, a.instalacion, a.origen, a.huella_p
    ):
        raise AprobacionInvalidaError("Identidad distinta")
    if (instante < emitida or instante - emitida >= timedelta(hours=24)
            or (a.ultimo_instante is not None and instante < _utc(a.ultimo_instante))):
        raise AprobacionInvalidaError("Reloj retrocedido o aprobación vencida")


def reservar(a: Aprobacion, *, intento: str, sha: str, head_inicial: str,
             instalacion: str, origen: str, huella_p: str, ahora: datetime,
             reloj_fiable: bool) -> Aprobacion:
    """Reserva una aprobación libre para exactamente un identificador de intento."""
    _validar(a, sha=sha, head_inicial=head_inicial, instalacion=instalacion,
             origen=origen, huella_p=huella_p, ahora=ahora, reloj_fiable=reloj_fiable)
    if a.estado is not Estado.AUTORIZADA or not _identidad(intento):
        raise AprobacionInvalidaError("Aprobación no reservable")
    return replace(a, estado=Estado.RESERVADA, intento=intento, ultimo_instante=ahora)


def consumir(a: Aprobacion, *, intento: str, sha: str, head_inicial: str,
             instalacion: str, origen: str, huella_p: str, ahora: datetime,
             reloj_fiable: bool) -> Aprobacion:
    """Revalida la reserva y la consume; no implica que se haya persistido."""
    _validar(a, sha=sha, head_inicial=head_inicial, instalacion=instalacion,
             origen=origen, huella_p=huella_p, ahora=ahora, reloj_fiable=reloj_fiable)
    if a.estado is not Estado.RESERVADA or not _identidad(intento) or a.intento != intento:
        raise AprobacionInvalidaError("Reserva inválida")
    return replace(a, estado=Estado.CONSUMIDA, ultimo_instante=ahora)


def marcar_incierta(a: Aprobacion, *, intento: str) -> Aprobacion:
    """Bloquea una reserva o consumo ambiguo; no existe liberación automática."""
    if not isinstance(a, Aprobacion) or a.estado not in (Estado.RESERVADA, Estado.CONSUMIDA):
        raise AprobacionInvalidaError("Estado no marcable como incierto")
    if not _identidad(intento) or intento != a.intento:
        raise AprobacionInvalidaError("Intento distinto")
    return replace(a, estado=Estado.INCIERTA)
