"""Motor de consolidación por campo para números (CCM-4).

Misma política que las series, con la precaución añadida de que un ID de issue
solo se usa si está asociado explícitamente: no se empareja por número.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from zascarr.core.consolidacion.ambitos import (
    CAMPOS_ISSUE,
    Ambito,
    RolVinculo,
)
from zascarr.core.consolidacion.motor import (
    CambioCampo,
    CandidatoCampo,
    PlanConsolidacion,
    RegistroFuente,
)
from zascarr.core.consolidacion.politicas import POLITICA_VERSION, orden_fuentes, rango
from zascarr.core.consolidacion.vocabulario import valor_comparable


@dataclass(frozen=True)
class EstadoIssue:
    id: str
    tradition: str | None
    language: str | None
    actuales: dict[str, Any]
    locked: frozenset[str]
    updated_at: str = ""


def _fuente_actual(prov: dict[str, Any] | None) -> str | None:
    if isinstance(prov, dict) and prov.get("source"):
        return str(prov["source"])
    return None


def _descartado(prov: dict[str, Any] | None, fuente: str, valor: Any) -> bool:
    if not isinstance(prov, dict):
        return False
    entrada = (prov.get("descartados") or {}).get(fuente)
    return isinstance(entrada, dict) and entrada.get("valor_descartado") == valor


def _candidatos(estado: EstadoIssue, registros: tuple[RegistroFuente, ...]
                ) -> dict[str, list[CandidatoCampo]]:
    salida: dict[str, list[CandidatoCampo]] = {}
    for registro in registros:
        for campo, ambito in CAMPOS_ISSUE.items():
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


def _cambios(estado: EstadoIssue, registros: tuple[RegistroFuente, ...],
             procedencias: dict[str, dict[str, Any] | None]) -> tuple[CambioCampo, ...]:
    candidatos = _candidatos(estado, registros)
    cambios: list[CambioCampo] = []
    for campo, ambito in CAMPOS_ISSUE.items():
        actual = estado.actuales.get(campo)
        comparable = valor_comparable(campo, actual)
        proc = procedencias.get(campo)
        fuente = _fuente_actual(proc)
        lista = tuple(candidatos.get(campo, ()))
        if campo in estado.locked:
            cambios.append(CambioCampo(campo, ambito, "bloqueado", actual, fuente, lista,
                                       motivo="locked_fields"))
            continue
        if isinstance(proc, dict) and (proc.get("source") == "manual"
                                       or proc.get("confianza") == "manual"):
            cambios.append(CambioCampo(campo, ambito, "bloqueado", actual, fuente, lista,
                                       motivo="manual"))
            continue
        if campo == "title" and comparable is not None:
            cambios.append(CambioCampo(campo, ambito, "conservar", actual, fuente, lista,
                                       motivo="titulo_local"))
            continue
        if comparable is None:
            cambios.append(CambioCampo(
                campo, ambito,
                "anadir" if lista else "sin_dato", actual, fuente, lista,
                lista[0] if lista else None))
            continue
        if isinstance(proc, dict) and (proc.get("confianza") == "legado"
                                       or proc.get("verificado") is False):
            cambios.append(CambioCampo(campo, ambito, "conservar", actual, fuente, lista,
                                       motivo="legado"))
            continue
        propios = [c for c in lista if c.fuente == fuente]
        if propios:
            elegido = propios[0]
            cambios.append(CambioCampo(
                campo, ambito,
                "acuerdo" if elegido.valor == comparable else "actualizar_misma_fuente",
                actual, fuente, lista,
                None if elegido.valor == comparable else elegido))
            continue
        if any(c.valor == comparable for c in lista):
            cambios.append(CambioCampo(campo, ambito, "acuerdo", actual, fuente, lista))
            continue
        restantes = [c for c in lista if not _descartado(proc, c.fuente, c.valor)]
        if not restantes:
            cambios.append(CambioCampo(campo, ambito, "conservar", actual, fuente, lista,
                                       motivo="descartado"))
        elif fuente is None:
            cambios.append(CambioCampo(campo, ambito, "conservar", actual, None, lista,
                                       motivo="origen_desconocido"))
        else:
            cambios.append(CambioCampo(campo, ambito, "conflicto", actual, fuente, lista))
    return tuple(cambios)


def huella_issue(estado: EstadoIssue, registros: tuple[RegistroFuente, ...],
                 procedencias: dict[str, dict[str, Any] | None]) -> str:
    base = {
        "entidad": estado.id, "updated_at": estado.updated_at,
        "actuales": estado.actuales, "locked": sorted(estado.locked),
        "procedencias": procedencias, "politica": POLITICA_VERSION,
        "registros": sorted([r.fuente, r.external_id, r.payload_hash, r.rol]
                            for r in registros),
    }
    return hashlib.sha256(json.dumps(base, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), default=str).encode()).hexdigest()


def construir_plan_issue(
    estado: EstadoIssue,
    registros: tuple[RegistroFuente, ...] | list[RegistroFuente],
    procedencias: dict[str, dict[str, Any] | None] | None = None,
    *, ahora: datetime | None = None,
) -> PlanConsolidacion:
    lista = tuple(registros)
    prov = procedencias or {}
    return PlanConsolidacion(
        entidad="issue", entity_id=estado.id, politica_version=POLITICA_VERSION,
        generado_en=ahora or datetime.now(UTC),
        huella=huella_issue(estado, lista, prov),
        cambios=_cambios(estado, lista, prov),
    )
