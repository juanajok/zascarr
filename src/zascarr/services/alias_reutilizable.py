# ruff: noqa: E501
"""MIT-M7 #132-a: ciclo de vida de alias aprendidos e importados.

Solo escribe las filas de alias: no crea ni modifica series, archivos,
declaraciones, correspondencias ni vínculos. El alias importado no lo consume
el matcher en esta entrega.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.matcher import normalize_title
from zascarr.models import (
    AliasImportado,
    EstadoAlias,
    LocalAlias,
    OrigenAlias,
    Series,
)


class AliasError(Exception):
    """Error de negocio con mensaje en español."""


class AliasNoEncontradoError(AliasError):
    pass


class AliasRetiradoError(AliasError):
    pass


class AliasConflictoError(AliasError):
    pass


class AliasInvalidoError(AliasError):
    pass


def evento(fila: LocalAlias | AliasImportado, motivo: str) -> dict:
    return {
        "version": fila.version,
        "estado": fila.estado.value if hasattr(fila.estado, "value") else fila.estado,
        "origen": fila.origen.value if hasattr(fila.origen, "value") else fila.origen,
        "series_id": str(fila.series_id),
        "scope_path": fila.scope_path,
        "fecha": datetime.now(UTC).isoformat(),
        "motivo": motivo,
    }


def _append_historial(fila: LocalAlias, motivo: str) -> None:
    historial = list(fila.historial or [])
    historial.append(evento(fila, motivo))
    fila.historial = historial
    fila.actualizado_en = datetime.now(UTC)


async def _local(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    fila = await db.get(LocalAlias, alias_id)
    if fila is None:
        raise AliasNoEncontradoError("Ese alias ya no existe.")
    return fila


async def listar_aprendidos(db: AsyncSession) -> list[LocalAlias]:
    return list((await db.execute(
        select(LocalAlias).order_by(LocalAlias.pattern_norm))).scalars().all())


async def historial_aprendido(db: AsyncSession, alias_id: UUID) -> list[dict]:
    return list((await _local(db, alias_id)).historial or [])


async def _cambiar_estado_local(db: AsyncSession, alias_id: UUID,
                                estado: EstadoAlias, motivo: str) -> LocalAlias:
    fila = await _local(db, alias_id)
    if fila.estado is EstadoAlias.RETIRADO:
        raise AliasRetiradoError("Un alias retirado no se puede reactivar.")
    if fila.estado is estado:
        return fila
    fila.estado = estado
    fila.version += 1
    _append_historial(fila, motivo)
    await db.commit()
    await db.refresh(fila)
    return fila


async def activar_aprendido(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    return await _cambiar_estado_local(db, alias_id, EstadoAlias.ACTIVO, "activacion")


async def desactivar_aprendido(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    return await _cambiar_estado_local(db, alias_id, EstadoAlias.DESACTIVADO, "desactivacion")


async def retirar_aprendido(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    fila = await _local(db, alias_id)
    if fila.estado is EstadoAlias.RETIRADO:
        return fila
    fila.estado = EstadoAlias.RETIRADO
    fila.version += 1
    _append_historial(fila, "retirada")
    await db.commit()
    await db.refresh(fila)
    return fila


async def _importado(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    fila = (await db.execute(
        select(AliasImportado).where(
            AliasImportado.alias_id == alias_id,
            AliasImportado.vigente_hasta.is_(None)).with_for_update())).scalar_one_or_none()
    if fila is None:
        raise AliasNoEncontradoError("Ese alias importado ya no existe.")
    return fila


def _fila_importada(*, alias_id: UUID, version: int, patron_norm: str,
                    scope_path: str | None, series_id: UUID, estado: EstadoAlias,
                    procedencia: dict, ahora: datetime) -> AliasImportado:
    return AliasImportado(
        id=uuid4(), alias_id=alias_id, version=version, patron_norm=patron_norm,
        scope_path=scope_path, series_id=series_id, origen=OrigenAlias.IMPORTADO,
        estado=estado, vigente_desde=ahora, vigente_hasta=None,
        procedencia=dict(procedencia))


async def crear_importado(db: AsyncSession, *, patron: str, series_id: UUID,
                          scope_path: str | None = None,
                          procedencia: dict | None = None) -> AliasImportado:
    patron_norm = normalize_title(patron)
    if not patron_norm:
        raise AliasInvalidoError("El patrón del alias no puede estar vacío.")
    if await db.get(Series, series_id) is None:
        raise AliasInvalidoError("La serie de destino no existe.")
    fila = _fila_importada(alias_id=uuid4(), version=1, patron_norm=patron_norm,
                           scope_path=scope_path, series_id=series_id,
                           estado=EstadoAlias.PROPUESTO,
                           procedencia=dict(procedencia or {}), ahora=datetime.now(UTC))
    db.add(fila)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AliasConflictoError("Ya existe un alias importado activo para ese patrón.") from exc
    await db.refresh(fila)
    return fila


async def listar_importados(db: AsyncSession, *, incluir_historial: bool = False) -> list[AliasImportado]:
    consulta = select(AliasImportado)
    if not incluir_historial:
        consulta = consulta.where(AliasImportado.vigente_hasta.is_(None))
    return list((await db.execute(
        consulta.order_by(AliasImportado.patron_norm, AliasImportado.version))).scalars().all())


async def historial_importado(db: AsyncSession, alias_id: UUID) -> list[AliasImportado]:
    return list((await db.execute(
        select(AliasImportado).where(AliasImportado.alias_id == alias_id)
        .order_by(AliasImportado.version))).scalars().all())


async def _nueva_version_importada(db: AsyncSession, actual: AliasImportado,
                                   estado: EstadoAlias, motivo: str,
                                   *, series_id: UUID | None = None,
                                   scope_path: str | None = None,
                                   patron_norm: str | None = None) -> AliasImportado:
    nuevo_patron = patron_norm or actual.patron_norm
    nuevo_scope = scope_path if scope_path is not None else actual.scope_path
    if estado is EstadoAlias.ACTIVO:
        ocupado = (await db.execute(
            select(AliasImportado.id).where(
                AliasImportado.patron_norm == nuevo_patron,
                func.coalesce(AliasImportado.scope_path, "") == (nuevo_scope or ""),
                AliasImportado.estado == EstadoAlias.ACTIVO,
                AliasImportado.vigente_hasta.is_(None),
                AliasImportado.alias_id != actual.alias_id))).scalar_one_or_none()
        if ocupado is not None:
            raise AliasConflictoError("Ya existe otro alias importado activo para ese patrón.")
    actual.vigente_hasta = datetime.now(UTC)
    nueva = _fila_importada(
        alias_id=actual.alias_id, version=actual.version + 1,
        patron_norm=patron_norm or actual.patron_norm,
        scope_path=scope_path if scope_path is not None else actual.scope_path,
        series_id=series_id or actual.series_id, estado=estado,
        procedencia=dict(actual.procedencia or {}), ahora=datetime.now(UTC))
    db.add(nueva)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise AliasConflictoError("Ya existe otro alias importado activo para ese patrón.") from exc
    await db.refresh(nueva)
    return nueva


async def activar_importado(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    actual = await _importado(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        raise AliasRetiradoError("Un alias retirado no se puede reactivar.")
    if actual.estado is EstadoAlias.ACTIVO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.ACTIVO, "activacion")


async def desactivar_importado(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    actual = await _importado(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        raise AliasRetiradoError("Un alias retirado no se puede desactivar.")
    if actual.estado is EstadoAlias.DESACTIVADO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.DESACTIVADO, "desactivacion")


async def retirar_importado(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    actual = await _importado(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.RETIRADO, "retirada")


async def cambiar_importado(db: AsyncSession, alias_id: UUID, *, patron: str | None = None,
                            series_id: UUID | None = None,
                            scope_path: str | None = None) -> AliasImportado:
    actual = await _importado(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        raise AliasRetiradoError("Un alias retirado no se puede cambiar.")
    if series_id is not None and await db.get(Series, series_id) is None:
        raise AliasInvalidoError("La serie de destino no existe.")
    patron_norm = normalize_title(patron) if patron is not None else None
    if patron is not None and not patron_norm:
        raise AliasInvalidoError("El patrón del alias no puede estar vacío.")
    return await _nueva_version_importada(
        db, actual, actual.estado, "cambio", series_id=series_id,
        scope_path=scope_path if scope_path is not None else actual.scope_path,
        patron_norm=patron_norm)
