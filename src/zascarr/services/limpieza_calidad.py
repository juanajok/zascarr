# ruff: noqa: E501
"""Lotes L2, L3 y L4 del informe de calidad, a demanda.

- **L3 (D6a):** archivos pendientes que no aparecen en «Por revisar» porque
  `metadata.match_status` no es `unsorted`; se les devuelve a la cola y se
  guarda el valor anterior en `metadata.match_status_previo`.
- **L2 (A1a):** archivos con `metadata.vinculo` que apunta a una serie que ya
  no existe; se retira el vínculo y se conserva en `metadata.vinculo_historial`
  con un `deshecho` (la procedencia no se pierde).
- **L4 (F5):** nombres de `locked_fields` que no existen en el modelo; se
  retiran. No protegían nada.

No lo lanza ningún ciclo. La vista previa no escribe; `aplicar` cambia un lote
pequeño por vez, en la transacción de la sesión. No toca identidad, número,
formato, archivos ni `issue_id`; solo el campo indicado por cada lote.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Character, Creator, File, Issue, Series

LOTE = 100
MUESTRA = 20
Lote = Literal["l3", "l2", "l4"]
LOTES: tuple[Lote, ...] = ("l3", "l2", "l4")

#: Los nombres válidos son las columnas reales del modelo: si el modelo cambia,
#: esta comprobación no se queda atrás (misma idea que el check F5 del censo).
_CAMPOS = {
    "serie": set(Series.__table__.columns.keys()),
    "issue": set(Issue.__table__.columns.keys()),
    "creator": set(Creator.__table__.columns.keys()),
    "character": set(Character.__table__.columns.keys()),
}


@dataclass(frozen=True)
class Muestra:
    id: str
    detalle: dict


@dataclass(frozen=True)
class VistaPrevia:
    lote: str
    pendientes: int
    muestra: tuple[Muestra, ...]


@dataclass(frozen=True)
class Resultado:
    lote: str
    limite: int
    pendientes_antes: int
    leidas: int
    cambiadas: int
    pendientes_despues: int


def _l3_condiciones():
    return (
        File.issue_id.is_(None),
        File.review_dismissed.is_(False),
        func.coalesce(File.metadata_["match_status"].astext, "") != "unsorted",
    )


#: `metadata.vinculo.serie_id` no existe en `series` (comparación en texto: el
#: campo se guarda como string y las series son UUID).
_L2_CONDICION = text(
    "jsonb_typeof(files.metadata -> 'vinculo') = 'object' "
    "AND files.metadata -> 'vinculo' ? 'serie_id' "
    "AND NOT EXISTS (SELECT 1 FROM series s "
    "WHERE s.id::text = lower(files.metadata -> 'vinculo' ->> 'serie_id'))"
)


def _l4_invalidos(fila) -> list[str]:
    validos = _CAMPOS[_entidad_de(fila)]
    return [c for c in (fila.locked_fields or []) if c and c not in validos]


def _entidad_de(fila) -> str:
    if isinstance(fila, Series):
        return "serie"
    if isinstance(fila, Issue):
        return "issue"
    if isinstance(fila, Creator):
        return "creator"
    return "character"


def _l4_entidades():
    return ((Series, "serie"), (Issue, "issue"), (Creator, "creator"), (Character, "character"))


class LimpiezaCalidad:
    """Vista previa y aplicación de un lote pequeño, sobre una sesión abierta."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def contar(self, lote: Lote) -> int:
        if lote == "l3":
            return int((await self._db.execute(
                select(func.count()).select_from(File).where(*_l3_condiciones())
            )).scalar_one())
        if lote == "l2":
            return int((await self._db.execute(
                select(func.count()).select_from(File).where(_L2_CONDICION)
            )).scalar_one())
        total = 0
        for modelo, _ in _l4_entidades():
            filas = (await self._db.execute(
                select(modelo).where(func.cardinality(modelo.locked_fields) > 0)
            )).scalars().all()
            total += sum(1 for f in filas if _l4_invalidos(f))
        return total

    async def previsualizar(self, lote: Lote, limite: int = MUESTRA) -> VistaPrevia:
        if lote == "l3":
            filas = (await self._db.execute(
                select(File).where(*_l3_condiciones()).order_by(File.id).limit(max(0, limite))
            )).scalars().all()
            muestra = tuple(Muestra(str(f.id), {"archivo": f.file_name,
                                                "match_status": (f.metadata_ or {}).get("match_status")})
                            for f in filas)
        elif lote == "l2":
            filas = (await self._db.execute(
                select(File).where(_L2_CONDICION).order_by(File.id).limit(max(0, limite))
            )).scalars().all()
            muestra = tuple(Muestra(str(f.id), {"archivo": f.file_name,
                                                "serie_id": ((f.metadata_ or {}).get("vinculo") or {}).get("serie_id")})
                            for f in filas)
        else:
            muestra_l: list[Muestra] = []
            for modelo, _ in _l4_entidades():
                filas = (await self._db.execute(
                    select(modelo).where(func.cardinality(modelo.locked_fields) > 0)
                )).scalars().all()
                for f in filas:
                    malos = _l4_invalidos(f)
                    if malos and len(muestra_l) < limite:
                        muestra_l.append(Muestra(str(f.id), {"entidad": _entidad_de(f), "campos": malos}))
            muestra = tuple(muestra_l)
        return VistaPrevia(lote=lote, pendientes=await self.contar(lote), muestra=muestra)

    async def aplicar(self, lote: Lote, limite: int = LOTE) -> Resultado:
        pendientes_antes = await self.contar(lote)
        if lote == "l3":
            filas = (await self._db.execute(
                select(File).where(*_l3_condiciones()).order_by(File.id)
                .with_for_update(skip_locked=True).limit(max(0, limite))
            )).scalars().all()
            for f in filas:
                meta = dict(f.metadata_ or {})
                meta["match_status_previo"] = meta.get("match_status")
                meta["match_status"] = "unsorted"
                f.metadata_ = meta
            cambiadas = len(filas)
        elif lote == "l2":
            filas = (await self._db.execute(
                select(File).where(_L2_CONDICION).order_by(File.id)
                .with_for_update(skip_locked=True).limit(max(0, limite))
            )).scalars().all()
            cambiadas = 0
            for f in filas:
                meta = dict(f.metadata_ or {})
                vinculo = meta.pop("vinculo", None)
                if not isinstance(vinculo, dict):
                    continue
                historial = meta.get("vinculo_historial")
                historial = list(historial) if isinstance(historial, list) else []
                historial.append({**vinculo, "deshecho": {
                    "operacion_id": str(uuid4()),
                    "fecha": datetime.now(UTC).isoformat(),
                    "motivo": "serie_borrada",
                }})
                meta["vinculo_historial"] = historial
                f.metadata_ = meta
                cambiadas += 1
        else:
            cambiadas = 0
            for modelo, _ in _l4_entidades():
                filas = (await self._db.execute(
                    select(modelo).where(func.cardinality(modelo.locked_fields) > 0)
                    .with_for_update(skip_locked=True).limit(max(0, limite - cambiadas))
                )).scalars().all()
                for f in filas:
                    malos = _l4_invalidos(f)
                    if not malos:
                        continue
                    f.locked_fields = [c for c in f.locked_fields if c not in malos]
                    cambiadas += 1
                if cambiadas >= limite:
                    break
        await self._db.flush()
        return Resultado(lote=lote, limite=limite, pendientes_antes=pendientes_antes,
                         leidas=cambiadas, cambiadas=cambiadas,
                         pendientes_despues=await self.contar(lote))
