"""Contratos puros de la CCM: sin SQLAlchemy, sin httpx y sin I/O.

La CCM consulta **por identificador ya asociado**, nunca por título. Estos tipos
separan la evidencia recolectada (`FichaRecolectada`) de la decisión de
consolidación, que llega en fases posteriores.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol


class EstadoFetch(StrEnum):
    """Resultado de una consulta a una fuente, sin ambigüedad."""

    OK = "ok"
    NO_MODIFICADO = "no_modificado"
    NO_ENCONTRADO = "no_encontrado"
    CUOTA_AGOTADA = "cuota_agotada"
    ERROR_RED = "error_red"
    ERROR_PARSEO = "error_parseo"


@dataclass(frozen=True)
class SugerenciaVinculo:
    """Un ID cruzado que una fuente declara; nunca se asocia solo."""

    fuente_destino: str
    external_id_destino: str
    evidencia: str


@dataclass(frozen=True)
class FichaRecolectada:
    """Evidencia normalizada de UNA fuente para UNA entidad."""

    fuente: str
    entidad: Literal["series", "issue"]
    external_id: str
    url: str | None
    licencia: str | None
    raw_acotado: dict[str, Any]
    normalizado: dict[str, Any]
    normalizer_version: int
    payload_hash: str
    observado_en: datetime
    sugerencias_id: tuple[SugerenciaVinculo, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ResultadoFetch:
    estado: EstadoFetch
    ficha: FichaRecolectada | None = None
    detalle_error: str | None = None
    reintentar_despues_de: datetime | None = None


class FuenteSeries(Protocol):
    """Contrato mínimo de una fuente para series (Fase 1).

    Los métodos de issue se añadirán en la Fase 4. No se incluye `search` a
    propósito: buscar por título no es una operación de la CCM.
    """

    nombre: str
    capacidades_serie: frozenset[str]

    async def fetch_serie(
        self, external_id: str, *, hash_previo: str | None = None
    ) -> ResultadoFetch: ...


def hash_payload(payload: dict[str, Any]) -> str:
    """Hash canónico del payload: el orden de claves no cambia la identidad."""
    crudo = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"), default=str)
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()
