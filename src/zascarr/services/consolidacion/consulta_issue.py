"""Carga del estado de un número y construcción de su plan (CCM-4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.consolidacion.ambitos import CAMPOS_ISSUE, rol_de
from zascarr.core.consolidacion.motor import PlanConsolidacion, RegistroFuente
from zascarr.core.consolidacion.motor_issue import EstadoIssue, construir_plan_issue
from zascarr.models import EntitySourceRecord, FieldProvenance, Issue, Series


class IssueNoEncontradoError(LookupError):
    pass


@dataclass(frozen=True)
class ContextoIssue:
    serie: Series
    issue: Issue
    estado: EstadoIssue
    registros: tuple[RegistroFuente, ...]
    procedencias: dict[str, dict[str, Any] | None]

    def plan(self) -> PlanConsolidacion:
        return construir_plan_issue(self.estado, self.registros, self.procedencias)


def _actual(issue: Issue) -> dict[str, Any]:
    return {campo: getattr(issue, campo, None) for campo in CAMPOS_ISSUE}


async def cargar_contexto_issue(db: AsyncSession, series_id: UUID,
                                issue_id: UUID) -> ContextoIssue:
    fila = (await db.execute(
        select(Issue, Series).join(Series, Issue.series_id == Series.id)
        .where(Issue.id == issue_id, Issue.series_id == series_id)
        .execution_options(populate_existing=True)
    )).first()
    if fila is None:
        raise IssueNoEncontradoError(str(issue_id))
    issue, serie = fila
    registros: list[RegistroFuente] = []
    for r in (await db.execute(
        select(EntitySourceRecord).where(
            EntitySourceRecord.entity_type == "issue",
            EntitySourceRecord.entity_id == issue_id,
        )
    )).scalars().all():
        payload = r.payload if isinstance(r.payload, dict) else {}
        normalizado = payload.get("normalizado")
        if not isinstance(normalizado, dict):
            continue
        registros.append(RegistroFuente(
            fuente=r.source, rol=rol_de(serie, r.source).value,
            external_id=r.external_id, normalizado=normalizado,
            url=r.source_url, licencia=r.license, payload_hash=r.payload_hash or "",
        ))
    provs = (await db.execute(
        select(FieldProvenance).where(
            FieldProvenance.entity_type == "issue",
            FieldProvenance.entity_id == issue_id,
        )
    )).scalars().all()
    procedencias = {p.field: (p.value if isinstance(p.value, dict) else None) for p in provs}
    estado = EstadoIssue(
        id=str(issue.id),
        tradition=str(getattr(serie.tradition, "value", serie.tradition or "")) or None,
        language=serie.language,
        actuales=_actual(issue),
        locked=frozenset(issue.locked_fields or []),
        updated_at=issue.updated_at.isoformat() if issue.updated_at else "",
    )
    return ContextoIssue(serie, issue, estado, tuple(registros), procedencias)
