# ruff: noqa: E501
"""Borrado de una serie (I4 de #114, ADR 0010 P-3).

El borrado es físico y solo opera sobre la BD: **no toca el disco** (ni mueve, ni renombra, ni borra ficheros). Antes
borraba en cascada números, deseados y alias y dejaba sin vincular los archivos, sin avisar. Ahora solo se borra una
serie **sin dependientes**; si algo depende de ella no se cambia nada y se dice por qué.

Motivos, en este orden (el primero que se cumple es el que se informa):

1. `operacion_viva`: hay una asignación de archivos en curso que apunta a la serie (el `409` que ya existía).
2. `tiene_archivos`: algún archivo está vinculado a un número de la serie.
3. `tiene_numeros`: la serie tiene números registrados.
4. `tiene_deseados`: tiene deseados o una política de búsqueda distinta de «ninguno».

Los alias locales y los géneros de la serie **sí** se borran con ella (son correspondencias hacia esa serie y no tienen
sentido sin ella). Los comprobantes de alta y los informes de vinculación no tienen clave foránea a `series`: se
conservan.

Bloqueos: la fila de la serie `FOR UPDATE`, el mismo orden que el «deshacer» del alta. Quien vincule archivos a números de
la serie la toma `FOR SHARE` (2d) y quien inserte en `issues` toma `FOR KEY SHARE` por la clave foránea: ambos esperan a
este borrado, o lo hacen esperar, y las comprobaciones se hacen sobre lo que ya está confirmado.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    ASIGNACION_ESTADOS_VIVOS,
    AsignacionOperacion,
    File,
    Issue,
    Series,
    Wishlist,
    WishlistPolicy,
)
from zascarr.services.asignacion import conflicto_por_operacion_viva

MENSAJES = {
    "operacion_viva": "Esta serie tiene una asignación de archivos en curso; espera a que termine "
                      "(o se reconcilie) e inténtalo de nuevo.",
    "tiene_archivos": "Esta serie tiene archivos vinculados, así que no se puede borrar. "
                      "Borrar una serie nunca toca los archivos del disco.",
    "tiene_numeros": "Esta serie tiene números registrados, así que no se puede borrar.",
    "tiene_deseados": "Esta serie tiene deseados o una política de búsqueda activa, así que no se puede borrar.",
}


class SerieNoEncontradaError(Exception):
    pass


class SerieNoBorrableError(Exception):
    """Algo depende de la serie. `motivo` es una de las claves de `MENSAJES`."""

    def __init__(self, motivo: str):
        super().__init__(MENSAJES[motivo])
        self.motivo = motivo


class BorradoDeSerie:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def borrar(self, series_id: UUID) -> None:
        """Borra la serie si no depende de ella nada. Confirma (o deshace) dentro: la respuesta refleja lo guardado."""
        try:
            await self._borrar_en_transaccion(series_id)
        except BaseException:
            await self._db.rollback()
            raise

    async def _borrar_en_transaccion(self, series_id: UUID) -> None:
        db = self._db
        serie = (await db.execute(select(Series).where(Series.id == series_id).with_for_update())).scalar_one_or_none()
        if serie is None:
            raise SerieNoEncontradaError(str(series_id))

        async def hay(consulta) -> bool:
            return bool((await db.execute(consulta.limit(1))).first())

        motivo = None
        if await hay(select(AsignacionOperacion.id).where(
                AsignacionOperacion.series_id == series_id,
                AsignacionOperacion.estado.in_(ASIGNACION_ESTADOS_VIVOS))):
            motivo = "operacion_viva"
        elif await hay(select(File.id).join(Issue, File.issue_id == Issue.id).where(Issue.series_id == series_id)):
            motivo = "tiene_archivos"
        elif await hay(select(Issue.id).where(Issue.series_id == series_id)):
            motivo = "tiene_numeros"
        elif serie.wishlist_policy != WishlistPolicy.NONE or await hay(
                select(Wishlist.id).where(Wishlist.series_id == series_id)):
            motivo = "tiene_deseados"
        if motivo is not None:
            raise SerieNoBorrableError(motivo)

        try:
            await db.delete(serie)
            # `flush` AQUÍ: un fallo de integridad debe llegar antes de responder, no en el `commit` de `get_db`.
            await db.flush()
        except IntegrityError as exc:
            # La restricción de la migración 0017 es la red de seguridad si una operación viva se colara.
            if conflicto_por_operacion_viva(exc):
                raise SerieNoBorrableError("operacion_viva") from exc
            raise                       # cualquier OTRO error de integridad NO es este conflicto
        await db.commit()
