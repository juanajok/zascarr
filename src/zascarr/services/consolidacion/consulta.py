"""Carga del estado de una serie y construcción del plan (CCM-2)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.core.consolidacion.ambitos import CAMPOS_SERIE, rol_de
from zascarr.core.consolidacion.motor import (
    EstadoSerie,
    PlanConsolidacion,
    RegistroFuente,
    construir_plan,
)
from zascarr.models import EntitySourceRecord, FieldProvenance, Series


class SerieNoEncontradaError(LookupError):
    pass


@dataclass(frozen=True)
class ContextoSerie:
    serie: Series
    estado: EstadoSerie
    registros: tuple[RegistroFuente, ...]
    procedencias: dict[str, dict[str, Any] | None]

    def plan(self) -> PlanConsolidacion:
        return construir_plan(self.estado, self.registros, self.procedencias)


def _valor_actual(serie: Series, campo: str) -> Any:
    if campo == "publisher_name":
        return serie.publisher.name if serie.publisher is not None else None
    return getattr(serie, campo, None)


def estado_de_serie(serie: Series, registros: tuple[RegistroFuente, ...],
                    procedencias: dict[str, dict[str, Any] | None]) -> EstadoSerie:
    return EstadoSerie(
        id=str(serie.id),
        tradition=str(getattr(serie.tradition, "value", serie.tradition or "")) or None,
        language=serie.language,
        actuales={campo: _valor_actual(serie, campo) for campo in CAMPOS_SERIE},
        locked=frozenset(serie.locked_fields or []),
        metadata=dict(serie.metadata_ or {}),
        updated_at=serie.updated_at.isoformat() if serie.updated_at else "",
    )


async def cargar_contexto(db: AsyncSession, series_id: UUID) -> ContextoSerie:
    serie = (await db.execute(
        select(Series).options(selectinload(Series.publisher))
        .where(Series.id == series_id)
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if serie is None:
        raise SerieNoEncontradaError(str(series_id))

    filas = (await db.execute(
        select(EntitySourceRecord).where(
            EntitySourceRecord.entity_type == "series",
            EntitySourceRecord.entity_id == series_id,
        )
    )).scalars().all()
    registros: list[RegistroFuente] = []
    for fila in filas:
        payload = fila.payload if isinstance(fila.payload, dict) else {}
        normalizado = payload.get("normalizado")
        if not isinstance(normalizado, dict):
            continue
        registros.append(RegistroFuente(
            fuente=fila.source, rol=rol_de(serie, fila.source).value,
            external_id=fila.external_id, normalizado=normalizado,
            url=fila.source_url, licencia=fila.license,
            payload_hash=fila.payload_hash or "",
        ))

    prov_filas = (await db.execute(
        select(FieldProvenance).where(
            FieldProvenance.entity_type == "series",
            FieldProvenance.entity_id == series_id,
        )
    )).scalars().all()
    procedencias: dict[str, dict[str, Any] | None] = {
        p.field: (p.value if isinstance(p.value, dict) else None) for p in prov_filas
    }
    return ContextoSerie(serie, estado_de_serie(serie, tuple(registros), procedencias),
                         tuple(registros), procedencias)
