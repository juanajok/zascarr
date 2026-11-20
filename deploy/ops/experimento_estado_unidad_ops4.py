"""Clasificador experimental de resultados de `systemctl start`; no ejecuta nada.

La observación es aportada por el llamador y no se verifica: código de salida,
estado textual y si la unidad estaba activa. Ante duda, el resultado es INCIERTO.
Un código distinto de cero no demuestra que la unidad no arrancase; un estado
`failed` no demuestra por sí solo que no hubiera efectos. No conectar a runtime.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ResultadoInicio(Enum):
    INICIADO = "iniciado"
    FALLIDO = "fallido"
    INCIERTO = "incierto"
    NO_DISPONIBLE = "no_disponible"


@dataclass(frozen=True)
class Observacion:
    codigo: object
    estado: object
    activo: object


_ESTADOS = frozenset({
    "active", "activating", "deactivating", "failed", "inactive", "reloading",
})


def clasificar_inicio(observacion: object) -> ResultadoInicio:
    """Clasificar de forma conservadora; no certifica que no hubiera efectos."""
    if not isinstance(observacion, Observacion):
        return ResultadoInicio.INCIERTO
    codigo = observacion.codigo
    estado = observacion.estado
    activo = observacion.activo
    if type(codigo) is not int or not isinstance(estado, str) or not isinstance(activo, bool):
        return ResultadoInicio.INCIERTO
    if estado == "not-found":
        return ResultadoInicio.NO_DISPONIBLE
    if estado not in _ESTADOS:
        return ResultadoInicio.INCIERTO
    if codigo != 0:
        # Un start no cero puede haber arrancado la unidad: nunca se declara inocuo.
        return ResultadoInicio.INCIERTO
    if activo and estado == "active":
        return ResultadoInicio.INICIADO
    if not activo and estado == "failed":
        return ResultadoInicio.FALLIDO
    return ResultadoInicio.INCIERTO
