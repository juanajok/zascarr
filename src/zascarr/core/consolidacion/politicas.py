"""Prioridad declarativa por tradición y ámbito (CCM-2)."""
from __future__ import annotations

from zascarr.core.consolidacion.ambitos import Ambito

POLITICA_VERSION = 1

#: Solo se incluyen fuentes con adaptador CCM. El orden no es global: se
#: elige por tradición y ámbito.
_PRIORIDAD_EDICION_ES = ("tebeosfera", "gcd", "open_library", "comic_vine",
                         "metron", "fandom_dc", "fandom_marvel", "anilist")
_PRIORIDAD_EDICION_US = ("comic_vine", "gcd", "metron", "open_library",
                         "fandom_dc", "fandom_marvel")
_PRIORIDAD_EDICION_MANGA = ("anilist", "tebeosfera", "open_library", "gcd")
_PRIORIDAD_EDICION_FUMETTI = ("metron", "tebeosfera", "gcd", "open_library")
_PRIORIDAD_OBRA = ("comic_vine", "fandom_dc", "fandom_marvel", "tebeosfera",
                   "gcd", "anilist", "metron", "open_library")


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
    trad = (tradicion or "").lower()
    if trad in {"manga", "manhwa", "manhua"}:
        return _PRIORIDAD_EDICION_MANGA
    if trad == "fumetti":
        return _PRIORIDAD_EDICION_FUMETTI
    return _PRIORIDAD_EDICION_US


def rango(fuente: str, orden: tuple[str, ...]) -> int:
    try:
        return orden.index(fuente)
    except ValueError:
        return len(orden)
