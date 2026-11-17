"""Aplicación transaccional del plan de la CCM (CCM-2).

No aplica conflictos ni valores bloqueados. Recalcula el plan dentro de la
transacción (`FOR UPDATE`) y aborta si la huella cambió entre la vista previa y
la escritura.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.core.consolidacion.motor import CambioCampo, PlanConsolidacion
from zascarr.models import FieldProvenance, Publisher, Series
from zascarr.services.consolidacion.consulta import (
    SerieNoEncontradaError,
    cargar_contexto,
)


class PlanCaducadoError(RuntimeError):
    """La entidad cambió después de la vista previa; no se escribe nada."""


@dataclass(frozen=True)
class ResultadoAplicacion:
    entity_id: str
    aplicados: int
    campos: tuple[str, ...]


class Aplicador:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def _series_bloqueada(self, series_id: UUID) -> Series:
        serie = (await self._db.execute(
            select(Series).options(selectinload(Series.publisher))
            .where(Series.id == series_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if serie is None:
            raise SerieNoEncontradaError(str(series_id))
        return serie

    async def _publisher(self, nombre: str, fuente: str) -> Publisher:
        existente = (await self._db.execute(
            select(Publisher).where(func.lower(Publisher.name) == nombre.casefold())
        )).scalar_one_or_none()
        if existente is not None:
            return existente
        nuevo = Publisher(name=nombre[:255], metadata_source=fuente)
        self._db.add(nuevo)
        await self._db.flush()
        return nuevo

    async def _aplicar_cambio(self, serie: Series, cambio: CambioCampo) -> bool:
        candidato = cambio.seleccionado
        if candidato is None:
            return False
        valor = candidato.valor
        if cambio.campo in {"start_year", "end_year", "total_issues"}:
            if not isinstance(valor, int):
                return False
            setattr(serie, cambio.campo, valor)
        elif cambio.campo == "language":
            serie.language = str(valor)[:10] if valor else None
        elif cambio.campo == "description":
            serie.description = str(valor) if valor else None
        elif cambio.campo == "publisher_name":
            serie.publisher = await self._publisher(str(valor), candidato.fuente)
        else:
            return False
        return True

    async def _marcar(self, serie: Series, cambio: CambioCampo) -> None:
        candidato = cambio.seleccionado
        if candidato is None:
            return
        previo = (await self._db.execute(
            select(FieldProvenance).where(
                FieldProvenance.entity_type == "series",
                FieldProvenance.entity_id == serie.id,
                FieldProvenance.field == cambio.campo,
            )
        )).scalar_one_or_none()
        descartados = (
            (previo.value or {}).get("descartados", {})
            if previo is not None and isinstance(previo.value, dict) else {}
        )
        valor = {
            "valor": candidato.valor,
            "ambito": cambio.ambito.value,
            "external_id": candidato.external_id,
            "url": candidato.url,
            "licencia": candidato.licencia,
            "confianza": "fuente",
            "descartados": descartados,
        }
        stmt = pg_insert(FieldProvenance).values(
            entity_type="series", entity_id=serie.id, field=cambio.campo,
            source=candidato.fuente, value=valor, fetched_at=datetime.now(UTC),
            locked=cambio.campo in (serie.locked_fields or []),
        ).on_conflict_do_update(
            index_elements=["entity_type", "entity_id", "field"],
            set_={"source": candidato.fuente, "value": valor,
                  "fetched_at": datetime.now(UTC),
                  "locked": cambio.campo in (serie.locked_fields or [])},
        )
        await self._db.execute(stmt)

    async def aplicar(
        self,
        plan: PlanConsolidacion,
        *,
        decisiones: dict[str, str] | None = None,
        solo_campos: set[str] | None = None,
    ) -> ResultadoAplicacion:
        """Aplica el plan fresco; una decisión explícita puede elegir un candidato.

        `decisiones` mapea campo → fuente. Solo se usan para conflictos que la
        persona ha resuelto en la vista previa; el resto sigue las reglas del
        motor.
        """
        serie = await self._series_bloqueada(UUID(plan.entity_id))
        contexto = await cargar_contexto(self._db, UUID(plan.entity_id))
        fresco = contexto.plan()
        if fresco.huella != plan.huella:
            raise PlanCaducadoError("La ficha cambió desde la vista previa; no se ha escrito nada.")
        elegidas = decisiones or {}
        aplicados: list[str] = []
        for cambio in fresco.cambios:
            if solo_campos is not None and cambio.campo not in solo_campos:
                continue
            if cambio.campo in elegidas:
                fuente = elegidas[cambio.campo]
                candidato = next(
                    (c for c in cambio.candidatos if c.fuente == fuente), None)
                if candidato is None:
                    continue
                cambio = replace(cambio, seleccionado=candidato)
            elif cambio.estado not in {"anadir", "actualizar_misma_fuente"}:
                continue
            if await self._aplicar_cambio(serie, cambio):
                await self._marcar(serie, cambio)
                aplicados.append(cambio.campo)
        await self._db.flush()
        return ResultadoAplicacion(str(serie.id), len(aplicados), tuple(aplicados))

    async def registrar_descarte(self, series_id: UUID, campo: str, fuente: str,
                                 valor: object | None = None) -> None:
        """Registra «mantener el mío» para que el conflicto no reaparezca."""
        serie = await self._series_bloqueada(series_id)
        contexto = await cargar_contexto(self._db, series_id)
        cambio = next((c for c in contexto.plan().cambios if c.campo == campo), None)
        candidato = next((c for c in (cambio.candidatos if cambio else ())
                          if c.fuente == fuente), None)
        valor_descartado = valor if valor is not None else (
            candidato.valor if candidato is not None else None)
        actual = (cambio.valor_actual if cambio is not None else None)
        previo = (await self._db.execute(
            select(FieldProvenance).where(
                FieldProvenance.entity_type == "series",
                FieldProvenance.entity_id == series_id,
                FieldProvenance.field == campo,
            )
        )).scalar_one_or_none()
        previo_valor = previo.value if previo is not None and isinstance(previo.value, dict) else {}
        descartados = dict(previo_valor.get("descartados") or {})
        descartados[fuente] = {
            "valor_descartado": valor_descartado,
            "resuelto_en": datetime.now(UTC).isoformat(timespec="seconds"),
            "motivo": "usuario_mantiene_actual",
        }
        dato = dict(previo_valor)
        dato.update({
            "valor": actual,
            "descartados": descartados,
            "confianza": previo_valor.get("confianza", "desconocido"),
            "ambito": (getattr(cambio, "ambito", None).value if cambio
                       else previo_valor.get("ambito")),
        })
        stmt = pg_insert(FieldProvenance).values(
            entity_type="series", entity_id=serie.id, field=campo,
            source=(previo.source if previo is not None else "desconocido"),
            value=dato, fetched_at=datetime.now(UTC),
            locked=campo in (serie.locked_fields or []),
        ).on_conflict_do_update(
            index_elements=["entity_type", "entity_id", "field"],
            set_={"value": dato, "fetched_at": datetime.now(UTC)},
        )
        await self._db.execute(stmt)
        await self._db.flush()
