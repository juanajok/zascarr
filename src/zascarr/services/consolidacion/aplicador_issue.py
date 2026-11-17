"""Aplicación transaccional del plan de número (CCM-4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.consolidacion.motor import CambioCampo, PlanConsolidacion
from zascarr.models import FieldProvenance, Issue
from zascarr.services.consolidacion.consulta_issue import (
    IssueNoEncontradoError,
    cargar_contexto_issue,
)


class PlanIssueCaducadoError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResultadoIssue:
    entity_id: str
    aplicados: int
    campos: tuple[str, ...]


class AplicadorIssue:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def _bloqueado(self, issue_id: UUID) -> Issue:
        issue = (await self._db.execute(
            select(Issue).where(Issue.id == issue_id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if issue is None:
            raise IssueNoEncontradoError(str(issue_id))
        return issue

    async def _marcar(self, issue: Issue, cambio: CambioCampo) -> None:
        cand = cambio.seleccionado
        if cand is None:
            return
        valor = {
            "valor": cand.valor, "ambito": cambio.ambito.value,
            "external_id": cand.external_id, "url": cand.url,
            "licencia": cand.licencia, "confianza": "fuente", "descartados": {},
        }
        stmt = pg_insert(FieldProvenance).values(
            entity_type="issue", entity_id=issue.id, field=cambio.campo,
            source=cand.fuente, value=valor, fetched_at=datetime.now(UTC),
            locked=cambio.campo in (issue.locked_fields or []),
        ).on_conflict_do_update(
            index_elements=["entity_type", "entity_id", "field"],
            set_={"source": cand.fuente, "value": valor,
                  "fetched_at": datetime.now(UTC),
                  "locked": cambio.campo in (issue.locked_fields or [])},
        )
        await self._db.execute(stmt)

    async def _aplicar(self, issue: Issue, cambio: CambioCampo) -> bool:
        cand = cambio.seleccionado
        if cand is None:
            return False
        if cambio.campo == "title":
            issue.title = str(cand.valor)[:500]
        elif cambio.campo == "release_date":
            try:
                issue.release_date = date.fromisoformat(str(cand.valor)[:10])
            except ValueError:
                return False
        elif cambio.campo == "page_count":
            if not isinstance(cand.valor, int) or not 1 <= cand.valor <= 10000:
                return False
            issue.page_count = cand.valor
        elif cambio.campo == "isbn":
            issue.isbn = str(cand.valor)[:20]
        elif cambio.campo == "synopsis":
            issue.synopsis = str(cand.valor)
        else:
            return False
        return True

    async def aplicar(self, plan: PlanConsolidacion) -> ResultadoIssue:
        issue = await self._bloqueado(UUID(plan.entity_id))
        contexto = await cargar_contexto_issue(self._db, issue.series_id, issue.id)
        fresco = contexto.plan()
        if fresco.huella != plan.huella:
            raise PlanIssueCaducadoError("El número cambió; no se ha escrito nada.")
        aplicados: list[str] = []
        for cambio in fresco.cambios_aplicables():
            if await self._aplicar(issue, cambio):
                await self._marcar(issue, cambio)
                aplicados.append(cambio.campo)
        if aplicados:
            metadata = dict(issue.metadata_ or {})
            metadata["comicinfo_sync_pendiente"] = True
            issue.metadata_ = metadata
        await self._db.flush()
        return ResultadoIssue(str(issue.id), len(aplicados), tuple(aplicados))

    async def registrar_descarte(self, issue_id: UUID, campo: str, fuente: str) -> None:
        issue = await self._bloqueado(issue_id)
        contexto = await cargar_contexto_issue(self._db, issue.series_id, issue.id)
        cambio = next((c for c in contexto.plan().cambios if c.campo == campo), None)
        cand = next((c for c in (cambio.candidatos if cambio else ())
                     if c.fuente == fuente), None)
        previo = (await self._db.execute(
            select(FieldProvenance).where(
                FieldProvenance.entity_type == "issue",
                FieldProvenance.entity_id == issue_id,
                FieldProvenance.field == campo)
        )).scalar_one_or_none()
        valor = dict(previo.value) if previo is not None and isinstance(previo.value, dict) else {}
        descartados = dict(valor.get("descartados") or {})
        descartados[fuente] = {
            "valor_descartado": cand.valor if cand is not None else None,
            "resuelto_en": datetime.now(UTC).isoformat(timespec="seconds"),
            "motivo": "usuario_mantiene_actual",
        }
        valor["descartados"] = descartados
        valor.setdefault("valor", getattr(issue, campo, None))
        valor.setdefault("ambito", cambio.ambito.value if cambio else "edition_scope")
        stmt = pg_insert(FieldProvenance).values(
            entity_type="issue", entity_id=issue.id, field=campo,
            source=(previo.source if previo is not None else "desconocido"),
            value=valor, fetched_at=datetime.now(UTC),
            locked=campo in (issue.locked_fields or []),
        ).on_conflict_do_update(
            index_elements=["entity_type", "entity_id", "field"],
            set_={"value": valor, "fetched_at": datetime.now(UTC)})
        await self._db.execute(stmt)
        await self._db.flush()
