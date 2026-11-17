"""Backfill conservador de `field_provenance` (CCM-2).

No aplica valores: solo deja constancia de lo que ya consta. La regla clave es
que `metadata_source` heredado se marca `legado`/no verificado y no se trata
como una fuente autoritativa de edición.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.core.consolidacion.ambitos import CAMPOS_SERIE
from zascarr.models import FieldProvenance, Series

_CAMPOS_COMICINFO = {"synopsis": "description"}


@dataclass
class InformeBackfill:
    series: int = 0
    filas: int = 0
    por_confianza: dict[str, int] = field(default_factory=dict)


def _valor_actual(serie: Series, campo: str) -> Any:
    if campo == "publisher_name":
        return serie.publisher.name if serie.publisher is not None else None
    return getattr(serie, campo, None)


def _vacio(valor: object) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def _origen(serie: Series, campo: str) -> tuple[str, str, bool, str | None]:
    """(fuente, confianza, verificado, url) para un campo no vacío."""
    metadata = serie.metadata_ if isinstance(serie.metadata_, dict) else {}
    manual = metadata.get("manual")
    if isinstance(manual, dict) and campo in manual:
        return "manual", "manual", True, None
    comicinfo = metadata.get("comicinfo_aplicado")
    if isinstance(comicinfo, dict):
        aplicado = comicinfo.get("aplicado")
        if isinstance(aplicado, dict):
            for clave, destino in _CAMPOS_COMICINFO.items():
                if aplicado.get(clave) is not None and destino == campo:
                    return "comicinfo_local", "local", True, None
    relleno = metadata.get("relleno")
    if isinstance(relleno, dict):
        for fuente, entrada in relleno.items():
            if not isinstance(entrada, dict):
                continue
            campos = entrada.get("campos")
            if isinstance(campos, list) and campo in campos:
                return str(fuente), "secundaria", True, (
                    str(entrada.get("url_ficha")) if entrada.get("url_ficha") else None)
    if campo in (serie.locked_fields or []):
        return "desconocido", "desconocido", False, None
    if serie.metadata_source:
        return str(serie.metadata_source), "legado", False, None
    return "desconocido", "desconocido", False, None


class Backfill:
    def __init__(self, db: AsyncSession, *, ahora: datetime | None = None):
        self._db = db
        self._ahora = ahora or datetime.now(UTC)

    async def ejecutar(self, limite: int | None = None) -> InformeBackfill:
        consulta = select(Series).options(selectinload(Series.publisher)).order_by(Series.id)
        if limite is not None:
            consulta = consulta.limit(max(0, limite))
        series = (await self._db.execute(consulta)).scalars().all()
        informe = InformeBackfill(series=len(series))
        for serie in series:
            for campo, ambito in CAMPOS_SERIE.items():
                valor = _valor_actual(serie, campo)
                if _vacio(valor):
                    continue
                fuente, confianza, verificado, url = _origen(serie, campo)
                dato = {
                    "valor": valor,
                    "ambito": ambito.value,
                    "confianza": confianza,
                    "verificado": verificado,
                    "legado": confianza == "legado",
                    "url": url,
                }
                statement = pg_insert(FieldProvenance).values(
                    entity_type="series", entity_id=serie.id, field=campo,
                    source=fuente, value=dato, fetched_at=self._ahora,
                    locked=campo in (serie.locked_fields or []),
                ).on_conflict_do_update(
                    index_elements=["entity_type", "entity_id", "field"],
                    set_={"source": fuente, "value": dato, "fetched_at": self._ahora,
                          "locked": campo in (serie.locked_fields or [])},
                )
                await self._db.execute(statement)
                informe.filas += 1
                informe.por_confianza[confianza] = informe.por_confianza.get(confianza, 0) + 1
        await self._db.flush()
        return informe
