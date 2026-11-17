"""Motor determinista de consolidación por campo (CCM-2).

Entrada: estado actual de una serie, procedencia conocida y fichas ya
recolectadas. Salida: un `PlanConsolidacion` reproducible. No importa
SQLAlchemy, no hace red y no escribe nada.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from zascarr.core.consolidacion.ambitos import (
    CAMPOS_SERIE,
    Ambito,
    RolVinculo,
)
from zascarr.core.consolidacion.politicas import (
    POLITICA_VERSION,
    orden_fuentes,
    rango,
)
from zascarr.core.consolidacion.vocabulario import valor_comparable

ESTADOS = (
    "anadir", "actualizar_misma_fuente", "acuerdo", "conservar",
    "conflicto", "bloqueado", "sin_dato",
)


@dataclass(frozen=True)
class RegistroFuente:
    fuente: str
    rol: str
    external_id: str
    normalizado: dict[str, Any]
    url: str | None = None
    licencia: str | None = None
    payload_hash: str = ""


@dataclass(frozen=True)
class EstadoSerie:
    id: str
    tradition: str | None
    language: str | None
    actuales: dict[str, Any]
    locked: frozenset[str]
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""


@dataclass(frozen=True)
class CandidatoCampo:
    campo: str
    valor: Any
    fuente: str
    external_id: str
    rol: str
    url: str | None
    licencia: str | None
    prioridad: int


@dataclass(frozen=True)
class CambioCampo:
    campo: str
    ambito: Ambito
    estado: str
    valor_actual: Any
    fuente_actual: str | None
    candidatos: tuple[CandidatoCampo, ...] = ()
    seleccionado: CandidatoCampo | None = None
    motivo: str | None = None


@dataclass(frozen=True)
class PlanConsolidacion:
    entidad: str
    entity_id: str
    politica_version: int
    generado_en: datetime
    huella: str
    cambios: tuple[CambioCampo, ...]

    def cambios_aplicables(self) -> tuple[CambioCampo, ...]:
        return tuple(c for c in self.cambios
                     if c.estado in {"anadir", "actualizar_misma_fuente"}
                     and c.seleccionado is not None)

    def conflictos(self) -> tuple[CambioCampo, ...]:
        return tuple(c for c in self.cambios if c.estado == "conflicto")


def _fuente_actual(procedencia: dict[str, Any] | None) -> str | None:
    if not isinstance(procedencia, dict):
        return None
    fuente = procedencia.get("source")
    return str(fuente) if fuente else None


def _descartado(procedencia: dict[str, Any] | None, fuente: str, valor: Any) -> bool:
    if not isinstance(procedencia, dict):
        return False
    descartados = procedencia.get("descartados")
    if not isinstance(descartados, dict):
        return False
    entrada = descartados.get(fuente)
    if not isinstance(entrada, dict):
        return False
    return entrada.get("valor_descartado") == valor


def _candidatos(estado: EstadoSerie, registros: tuple[RegistroFuente, ...]
                ) -> dict[str, list[CandidatoCampo]]:
    salida: dict[str, list[CandidatoCampo]] = {}
    for registro in registros:
        for campo, ambito in CAMPOS_SERIE.items():
            if ambito is Ambito.EDICION and registro.rol != RolVinculo.EDICION_PROPIA.value:
                continue
            bloque = registro.normalizado.get(ambito.value)
            if not isinstance(bloque, dict) or campo not in bloque:
                continue
            valor = valor_comparable(campo, bloque.get(campo))
            if valor is None:
                continue
            orden = orden_fuentes(estado.tradition, ambito, estado.language)
            salida.setdefault(campo, []).append(CandidatoCampo(
                campo=campo, valor=valor, fuente=registro.fuente,
                external_id=registro.external_id, rol=registro.rol,
                url=registro.url, licencia=registro.licencia,
                prioridad=rango(registro.fuente, orden),
            ))
    for lista in salida.values():
        lista.sort(key=lambda c: (c.prioridad, c.fuente, c.external_id))
    return salida


def _cambios(estado: EstadoSerie, registros: tuple[RegistroFuente, ...],
             procedencias: dict[str, dict[str, Any] | None]
             ) -> tuple[CambioCampo, ...]:
    candidatos = _candidatos(estado, registros)
    cambios: list[CambioCampo] = []
    for campo, ambito in CAMPOS_SERIE.items():
        actual = estado.actuales.get(campo)
        comparable_actual = valor_comparable(campo, actual)
        proc = procedencias.get(campo)
        fuente_actual = _fuente_actual(proc)
        lista = tuple(candidatos.get(campo, ()))
        if campo in estado.locked:
            cambios.append(CambioCampo(campo, ambito, "bloqueado", actual,
                                       fuente_actual, lista, motivo="locked_fields"))
            continue
        if (isinstance(proc, dict) and proc.get("source") == "manual") or (
                isinstance(proc, dict) and proc.get("confianza") == "manual"):
            cambios.append(CambioCampo(campo, ambito, "bloqueado", actual,
                                       fuente_actual, lista, motivo="manual"))
            continue
        # El título de una serie existente no se corrige automáticamente: es
        # identidad local y cambiaría la ficha y las búsquedas.
        if campo == "title" and comparable_actual is not None:
            cambios.append(CambioCampo(campo, ambito, "conservar", actual,
                                       fuente_actual, lista, motivo="titulo_local"))
            continue
        if comparable_actual is None:
            if not lista:
                cambios.append(CambioCampo(campo, ambito, "sin_dato", actual,
                                           fuente_actual, lista))
            else:
                cambios.append(CambioCampo(campo, ambito, "anadir", actual,
                                           fuente_actual, lista, lista[0]))
            continue
        # Un valor heredado/no verificado se conserva hasta revisión humana.
        if isinstance(proc, dict) and (
                proc.get("confianza") == "legado" or proc.get("verificado") is False):
            cambios.append(CambioCampo(campo, ambito, "conservar", actual,
                                       fuente_actual, lista, motivo="legado"))
            continue
        # Misma fuente: puede refrescar su propio dato.
        propios = [c for c in lista if fuente_actual == c.fuente]
        if propios:
            elegido = propios[0]
            if elegido.valor == comparable_actual:
                cambios.append(CambioCampo(campo, ambito, "acuerdo", actual,
                                           fuente_actual, lista))
            else:
                cambios.append(CambioCampo(campo, ambito, "actualizar_misma_fuente",
                                           actual, fuente_actual, lista, elegido))
            continue
        # Acuerdo entre fuentes distintas.
        acuerdan = [c for c in lista if c.valor == comparable_actual]
        if acuerdan:
            cambios.append(CambioCampo(campo, ambito, "acuerdo", actual,
                                       fuente_actual, lista))
            continue
        # Un conflicto ya descartado por la persona no vuelve a saltar.
        restantes = [c for c in lista if not _descartado(proc, c.fuente, c.valor)]
        if not restantes:
            cambios.append(CambioCampo(campo, ambito, "conservar", actual,
                                       fuente_actual, lista, motivo="descartado"))
            continue
        # Origen desconocido: no se pisa nunca.
        if fuente_actual is None:
            cambios.append(CambioCampo(campo, ambito, "conservar", actual, None,
                                       lista, motivo="origen_desconocido"))
            continue
        cambios.append(CambioCampo(campo, ambito, "conflicto", actual,
                                   fuente_actual, lista))
    return tuple(cambios)


def huella_plan(estado: EstadoSerie, registros: tuple[RegistroFuente, ...],
                procedencias: dict[str, dict[str, Any] | None] | None = None) -> str:
    base = {
        "entidad": estado.id,
        "updated_at": estado.updated_at,
        "locked": sorted(estado.locked),
        "actuales": estado.actuales,
        "procedencias": procedencias or {},
        "politica": POLITICA_VERSION,
        "registros": sorted(
            [r.fuente, r.external_id, r.payload_hash, r.rol] for r in registros
        ),
    }
    crudo = json.dumps(base, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(crudo.encode("utf-8")).hexdigest()


def construir_plan(
    estado: EstadoSerie,
    registros: tuple[RegistroFuente, ...] | list[RegistroFuente],
    procedencias: dict[str, dict[str, Any] | None] | None = None,
    *, ahora: datetime | None = None,
) -> PlanConsolidacion:
    """Construye el plan determinista. No escribe ni aplica nada."""
    lista = tuple(registros)
    cambios = _cambios(estado, lista, procedencias or {})
    return PlanConsolidacion(
        entidad="series", entity_id=estado.id,
        politica_version=POLITICA_VERSION,
        generado_en=ahora or datetime.now(UTC),
        huella=huella_plan(estado, lista, procedencias),
        cambios=cambios,
    )
