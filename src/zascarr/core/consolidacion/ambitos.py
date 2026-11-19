"""Ámbito de cada campo y rol de cada vínculo externo (CCM-2).

La regla de seguridad es deliberadamente simple: **sin rol explícito, un
vínculo es `obra_referencia`**. Así una ficha USA no puede rellenar los años,
el total ni la editorial de una edición española.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class Ambito(StrEnum):
    EDICION = "edition_scope"
    OBRA = "work_scope"


class RolVinculo(StrEnum):
    EDICION_PROPIA = "edicion_propia"
    OBRA_REFERENCIA = "obra_referencia"


#: Campos de serie que la Fase 2 puede consolidar. `imprint_name`, `country` y
#: `edition_kind` llegarán cuando exista resolución/validación propia.
CAMPOS_SERIE: dict[str, Ambito] = {
    "title": Ambito.EDICION,
    "start_year": Ambito.EDICION,
    "end_year": Ambito.EDICION,
    "publisher_name": Ambito.EDICION,
    "language": Ambito.EDICION,
    "total_issues": Ambito.EDICION,
    "description": Ambito.OBRA,
}

ROLES = frozenset({RolVinculo.EDICION_PROPIA.value, RolVinculo.OBRA_REFERENCIA.value})

#: Campos de número que la Fase 4 puede consolidar. `format` exige mapeo de
#: fuente a `IssueFormat`; se incorpora cuando exista esa normalización.
CAMPOS_ISSUE: dict[str, Ambito] = {
    "title": Ambito.EDICION,
    "release_date": Ambito.EDICION,
    "page_count": Ambito.EDICION,
    "isbn": Ambito.EDICION,
    "synopsis": Ambito.OBRA,
}


def campos_de(ambito: Ambito) -> tuple[str, ...]:
    return tuple(campo for campo, valor in CAMPOS_SERIE.items() if valor is ambito)


def rol_de(serie: Any, fuente: str) -> RolVinculo:
    """Rol explícito de un vínculo; por defecto, obra de referencia.

    No se infiere del idioma ni del título: el valor por defecto es el seguro.
    """
    metadata = getattr(serie, "metadata_", None)
    mapa = metadata.get("vinculos_rol") if isinstance(metadata, dict) else None
    valor = mapa.get(fuente) if isinstance(mapa, dict) else None
    if valor in ROLES:
        return RolVinculo(valor)
    return RolVinculo.OBRA_REFERENCIA


def rol_sugerido(serie: Any, fuente: str, normalizado: dict[str, Any]) -> RolVinculo:
    """Sugerencia para la UI; nunca se aplica sola.

    Tebeosfera se propone como edición propia cuando la serie ya tiene su slug;
    el resto se queda como obra de referencia hasta que la persona confirme.
    """
    if fuente == "tebeosfera" and getattr(serie, "tebeosfera_slug", None):
        return RolVinculo.EDICION_PROPIA
    return RolVinculo.OBRA_REFERENCIA
