"""Prioridad declarativa por tradición y ámbito (CCM-2)."""
from __future__ import annotations

from zascarr.core.consolidacion.ambitos import Ambito

POLITICA_VERSION = 1

#: Solo se incluyen fuentes que la Fase 2 puede recolectar; las demás no
#: aparecen hasta que sus adaptadores existan.
_PRIORIDAD_EDICION_ES = ("tebeosfera", "gcd", "comic_vine")
_PRIORIDAD_EDICION_US = ("comic_vine", "gcd")
_PRIORIDAD_OBRA = ("comic_vine", "tebeosfera", "gcd")


def es_edicion_es(tradicion: str | None, idioma: str | None) -> bool:
    return (idioma or "").lower() in {"es", "spa", "es-es"} or (
        (tradicion or "").lower() in {"tebeo", "franco_belgian"}
    )


def orden_fuentes(tradicion: str | None, ambito: Ambito,
                  idioma: str | None = None) -> tuple[str, ...]:
    if ambito is Ambito.OBRA:
        return _PRIORIDAD_OBRA
    if es_edicion_es(tradicion, idioma):
        return _PRIORIDAD_EDICION_ES
    return _PRIORIDAD_EDICION_US


def rango(fuente: str, orden: tuple[str, ...]) -> int:
    try:
        return orden.index(fuente)
    except ValueError:
        return len(orden)
