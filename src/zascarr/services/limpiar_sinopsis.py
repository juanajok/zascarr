# ruff: noqa: E501
"""L1/F4a (#1186): limpiar el HTML de las sinopsis ya guardadas.

A demanda, sin automatismo: no lo lanza ningún ciclo. La **vista previa** no
escribe; `aplicar` limpia en lotes de ≤100 filas, guarda el texto original en
`issues.metadata["sinopsis_original"]` y no toca las sinopsis protegidas
(`locked_fields` con `synopsis`) ni las de `metadata_source='manual'`.

Es idempotente: si el original ya está guardado no se pisa; si la sinopsis ya
es texto plano no se reescribe. No cambia identidad, número, formato ni
archivos: solo el texto de la sinopsis.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Issue, MetadataSource
from zascarr.utils.texto_html import texto_plano

#: Filas por lote de `aplicar` y muestra de la vista previa.
LOTE = 100
MUESTRA = 20

#: El MISMO patrón que la comprobación F4a del censo. Selecciona lo que la
#: medición contó como defecto; `texto_plano` decide el valor nuevo.
_PATRON = r"&(amp|lt|gt|quot|#39|nbsp);|</?[a-zA-Z][^>]*>"
_RE = re.compile(_PATRON)


def parece_html(texto: str | None) -> bool:
    """¿El texto tiene entidades o etiquetas HTML? (criterio de F4a)."""
    return bool(texto and _RE.search(texto))


def _locks(issue_locks):
    """Array de bloqueos, tratando NULL como vacío (filas antiguas)."""
    return func.coalesce(issue_locks, text("'{}'::varchar[]"))


def _candidatas():
    return (
        Issue.synopsis.is_not(None),
        Issue.synopsis.op("~")(_PATRON),
        Issue.metadata_source.is_distinct_from(MetadataSource.MANUAL.value),
        ~_locks(Issue.locked_fields).contains(["synopsis"]),
    )


def _protegidas():
    return (
        Issue.synopsis.is_not(None),
        Issue.synopsis.op("~")(_PATRON),
        _locks(Issue.locked_fields).contains(["synopsis"]),
    )


def _manuales():
    return (
        Issue.synopsis.is_not(None),
        Issue.synopsis.op("~")(_PATRON),
        Issue.metadata_source == MetadataSource.MANUAL.value,
    )


@dataclass(frozen=True)
class Muestra:
    issue_id: str
    antes: str
    despues: str


@dataclass(frozen=True)
class VistaPrevia:
    pendientes: int
    protegidas: int
    manuales: int
    muestra: tuple[Muestra, ...]


@dataclass(frozen=True)
class Resultado:
    limite: int
    pendientes_antes: int
    leidas: int
    limpiadas: int
    sin_cambio: int
    cambiadas: int
    pendientes_despues: int


class LimpiadorSinopsis:
    """Vista previa y limpieza de sinopsis con HTML, sobre una sesión abierta."""

    def __init__(self, db: AsyncSession):
        self._db = db

    async def contar(self) -> int:
        """Sinopsis candidatas (con HTML, no protegidas ni manuales)."""
        return int((await self._db.execute(
            select(func.count()).select_from(Issue).where(*_candidatas())
        )).scalar_one())

    async def _contar_con(self, condiciones) -> int:
        return int((await self._db.execute(
            select(func.count()).select_from(Issue).where(*condiciones)
        )).scalar_one())

    async def previsualizar(self, limite: int = MUESTRA) -> VistaPrevia:
        """Cuenta y enseña hasta `limite` antes/después. No escribe nada."""
        pendientes = await self.contar()
        protegidas = await self._contar_con(_protegidas())
        manuales = await self._contar_con(_manuales())
        filas = (await self._db.execute(
            select(Issue.id, Issue.synopsis)
            .where(*_candidatas())
            .order_by(Issue.id)
            .limit(max(0, limite))
        )).all()
        return VistaPrevia(
            pendientes=pendientes, protegidas=protegidas, manuales=manuales,
            muestra=tuple(
                Muestra(issue_id=str(issue_id), antes=antes, despues=texto_plano(antes))
                for issue_id, antes in filas
            ),
        )

    async def aplicar(self, limite: int = LOTE) -> Resultado:
        """Limpia hasta `limite` filas en la transacción de la sesión.

        No confirma: el llamador hace `commit` (o `rollback`). El `UPDATE` es
        condicional a que la sinopsis siga siendo la que se leyó; si otro
        proceso la cambió, la fila se cuenta como `cambiadas` y no se pisa.
        """
        pendientes_antes = await self.contar()
        filas = (await self._db.execute(
            select(Issue.id, Issue.synopsis, Issue.metadata_)
            .where(*_candidatas())
            .order_by(func.random())
            .limit(max(0, limite))
        )).all()
        limpiadas = sin_cambio = cambiadas = 0
        for issue_id, antes, metadata in filas:
            despues = texto_plano(antes) or None
            if despues == antes:
                sin_cambio += 1
                continue
            valores: dict[str, object] = {"synopsis": despues}
            if not (isinstance(metadata, dict) and "sinopsis_original" in metadata):
                valores["metadata_"] = (
                    func.coalesce(Issue.metadata_, text("'{}'::jsonb"))
                    .op("||")(func.jsonb_build_object("sinopsis_original", antes))
                )
            resultado = await self._db.execute(
                update(Issue)
                .where(Issue.id == issue_id, Issue.synopsis == antes)
                .values(**valores)
            )
            if resultado.rowcount == 1:
                limpiadas += 1
            else:
                cambiadas += 1
        await self._db.flush()
        pendientes_despues = await self.contar()
        return Resultado(
            limite=limite, pendientes_antes=pendientes_antes, leidas=len(filas),
            limpiadas=limpiadas, sin_cambio=sin_cambio, cambiadas=cambiadas,
            pendientes_despues=pendientes_despues,
        )
