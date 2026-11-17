"""Recolector de evidencia por ID (CCM Fase 1).

Escribe **solo** `entity_source_records`. No modifica `Series`/`Issue`, no
descarga portadas y no aplica metadatos. Una respuesta `NO_MODIFICADO` no
reescribe la fila; un error no borra el payload anterior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.consolidacion.tipos import (
    EstadoFetch,
    FichaRecolectada,
)
from zascarr.models import EntitySourceRecord, Issue, Series

#: Columna de `Series` que guarda el ID de cada fuente de la Fase 1.
COLUMNA_ID = {
    "comic_vine": "comic_vine_id",
    "tebeosfera": "tebeosfera_slug",
    "gcd": "gcd_id",
    "anilist": "anilist_id",
    "metron": "metron_id",
    "open_library": "open_library_id",
    "fandom_dc": "fandom_dc_slug",
    "fandom_marvel": "fandom_marvel_slug",
}
COLUMNA_ID_ISSUE = {
    "comic_vine": "comic_vine_id",
    "tebeosfera": "tebeosfera_slug",
    "gcd": "gcd_id",
    "fandom_dc": "fandom_dc_slug",
    "fandom_marvel": "fandom_marvel_slug",
}


@dataclass(frozen=True)
class ResultadoRecoleccion:
    fuente: str
    estado: EstadoFetch
    guardado: bool = False
    detalle: str | None = None


@dataclass
class InformeRecoleccion:
    series_id: str
    resultados: list[ResultadoRecoleccion] = field(default_factory=list)

    @property
    def guardados(self) -> int:
        return sum(1 for r in self.resultados if r.guardado)


class Recolector:
    """Orquesta adaptadores y el UPSERT de evidencia para una serie."""

    def __init__(self, db: AsyncSession, adaptadores: dict[str, Any], *,
                 ahora: datetime | None = None):
        self._db = db
        self._adaptadores = adaptadores
        self._ahora = ahora

    async def _hash_previo(self, entity_id: object, fuente: str,
                           external_id: str, *, entity_type: str = "series") -> str | None:
        return (await self._db.execute(
            select(EntitySourceRecord.payload_hash).where(
                EntitySourceRecord.entity_type == entity_type,
                EntitySourceRecord.entity_id == entity_id,
                EntitySourceRecord.source == fuente,
                EntitySourceRecord.external_id == external_id,
            )
        )).scalar_one_or_none()

    def _payload(self, ficha: FichaRecolectada) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "normalizer_version": ficha.normalizer_version,
            "raw_acotado": ficha.raw_acotado,
            "normalizado": ficha.normalizado,
            "sugerencias_id": [
                {"fuente_destino": s.fuente_destino,
                 "external_id_destino": s.external_id_destino,
                 "evidencia": s.evidencia}
                for s in ficha.sugerencias_id
            ],
        }

    async def _guardar(self, entity_id: object, ficha: FichaRecolectada, *,
                       entity_type: str = "series") -> None:
        statement = pg_insert(EntitySourceRecord).values(
            entity_type=entity_type,
            entity_id=entity_id,
            source=ficha.fuente,
            external_id=ficha.external_id,
            source_url=ficha.url,
            payload=self._payload(ficha),
            payload_hash=ficha.payload_hash,
            license=ficha.licencia,
            fetched_at=ficha.observado_en,
        ).on_conflict_do_update(
            constraint="uq_entity_source_record",
            set_={
                "source_url": ficha.url,
                "payload": self._payload(ficha),
                "payload_hash": ficha.payload_hash,
                "license": ficha.licencia,
                "fetched_at": ficha.observado_en,
            },
        )
        await self._db.execute(statement)
        await self._db.flush()

    async def recolectar_serie(self, series: Series) -> InformeRecoleccion:
        """Consulta las fuentes asociadas de una serie y guarda la evidencia."""
        informe = InformeRecoleccion(str(series.id))
        for fuente, adaptador in self._adaptadores.items():
            columna = COLUMNA_ID.get(fuente)
            if columna is None:
                continue
            externo = getattr(series, columna, None)
            if externo is None or str(externo).strip() == "":
                continue
            external_id = str(externo)
            try:
                previo = await self._hash_previo(series.id, fuente, external_id)
                resultado = await adaptador.fetch_serie(
                    external_id, hash_previo=previo)
            except Exception as exc:  # noqa: BLE001 — una fuente no tumba las demás
                informe.resultados.append(ResultadoRecoleccion(
                    fuente, EstadoFetch.ERROR_RED, detalle=type(exc).__name__))
                continue

            if resultado.estado is EstadoFetch.OK and resultado.ficha is not None:
                await self._guardar(series.id, resultado.ficha)
                informe.resultados.append(ResultadoRecoleccion(
                    fuente, resultado.estado, guardado=True))
            else:
                informe.resultados.append(ResultadoRecoleccion(
                    fuente, resultado.estado, detalle=resultado.detalle_error))
        return informe

    async def recolectar_lote(self, limite: int = 20) -> list[InformeRecoleccion]:
        """Recolecta las series que tengan algún ID de las fuentes de Fase 1."""
        series = (await self._db.execute(
            select(Series).where(
                (Series.comic_vine_id.is_not(None))
                | (Series.tebeosfera_slug.is_not(None))
                | (Series.gcd_id.is_not(None))
                | (Series.anilist_id.is_not(None))
                | (Series.metron_id.is_not(None))
                | (Series.open_library_id.is_not(None))
                | (Series.fandom_dc_slug.is_not(None))
                | (Series.fandom_marvel_slug.is_not(None))
            ).order_by(Series.id).limit(limite)
        )).scalars().all()
        informes: list[InformeRecoleccion] = []
        for serie in series:
            informes.append(await self.recolectar_serie(serie))
        return informes


    async def recolectar_issue(self, issue: Issue) -> InformeRecoleccion:
        """Consulta las fuentes asociadas de un número y guarda la evidencia."""
        informe = InformeRecoleccion(str(issue.id))
        for fuente, adaptador in self._adaptadores.items():
            columna = COLUMNA_ID_ISSUE.get(fuente)
            if columna is None:
                continue
            externo = getattr(issue, columna, None)
            if externo is None or str(externo).strip() == "":
                continue
            external_id = str(externo)
            try:
                previo = await self._hash_previo(
                    issue.id, fuente, external_id, entity_type="issue")
                resultado = await adaptador.fetch_issue(
                    external_id, hash_previo=previo)
            except Exception as exc:  # noqa: BLE001
                informe.resultados.append(ResultadoRecoleccion(
                    fuente, EstadoFetch.ERROR_RED, detalle=type(exc).__name__))
                continue
            if resultado.estado is EstadoFetch.OK and resultado.ficha is not None:
                await self._guardar(issue.id, resultado.ficha, entity_type="issue")
                informe.resultados.append(ResultadoRecoleccion(
                    fuente, resultado.estado, guardado=True))
            else:
                informe.resultados.append(ResultadoRecoleccion(
                    fuente, resultado.estado, detalle=resultado.detalle_error))
        return informe

    async def recolectar_lote_issues(self, limite: int = 20) -> list[InformeRecoleccion]:
        issues = (await self._db.execute(
            select(Issue).where(
                (Issue.comic_vine_id.is_not(None))
                | (Issue.tebeosfera_slug.is_not(None))
                | (Issue.gcd_id.is_not(None))
                | (Issue.fandom_dc_slug.is_not(None))
                | (Issue.fandom_marvel_slug.is_not(None))
            ).order_by(Issue.id).limit(limite)
        )).scalars().all()
        return [await self.recolectar_issue(issue) for issue in issues]
