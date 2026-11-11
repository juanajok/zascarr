"""MIT-M7-US03 (#132): ciclo de vida de alias aprendidos e importados.

Los alias **aprendidos** (B13) pasan a tener consentimiento explícito: nacen
`propuesto` y no se aplican hasta que la persona los activa. Los alias de
**importación** son versionados por filas y quedan subordinados a las decisiones
locales; en #132 no tienen consumidor en el matcher (solo administración).

Todo es aditivo: no se toca series, issues, archivos, declaraciones ni
correspondencias. Activar/desactivar/retirar no reasigna nada ya confirmado.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import AliasImportado, EstadoAlias, LocalAlias, OrigenAlias


class AliasNoEncontradoError(LookupError):
    pass


class TransicionInvalidaError(ValueError):
    pass


def _ahora() -> datetime:
    return datetime.now(UTC)


def _evento(alias: LocalAlias, motivo: str, **extra) -> dict:
    return {
        "version": alias.version,
        "estado": getattr(alias.estado, "value", alias.estado),
        "origen": getattr(alias.origen, "value", alias.origen),
        "series_id": str(alias.series_id),
        "scope_path": alias.scope_path,
        "fecha": _ahora().isoformat(),
        "motivo": motivo,
        **extra,
    }


def _aplicar(alias: LocalAlias, estado: EstadoAlias, motivo: str) -> None:
    """Cambia estado/versión y añade el evento al historial (sin commit)."""
    alias.version = (alias.version or 0) + 1
    alias.estado = estado
    alias.actualizado_en = _ahora()
    alias.historial = [*(alias.historial or []), _evento(alias, motivo)]


async def _local(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    alias = await db.get(LocalAlias, alias_id)
    if alias is None:
        raise AliasNoEncontradoError("Ese alias ya no existe.")
    return alias


def _exigir_confirmacion(confirmado: bool) -> None:
    if not confirmado:
        raise TransicionInvalidaError(
            "Activar un alias necesita una confirmación explícita e independiente.")


async def aprender_alias(db: AsyncSession, pattern_norm: str, series_id: UUID) -> LocalAlias:
    """Aprende un alias SIN activarlo (flush, no commit: va dentro de la transacción
    de la asignación). Nunca pisa un alias activo con otra serie: deja un conflicto."""
    existente = (await db.execute(
        select(LocalAlias).where(LocalAlias.pattern_norm == pattern_norm)
    )).scalar_one_or_none()
    if existente is None:
        nuevo = LocalAlias(pattern_norm=pattern_norm, series_id=series_id,
                           origen=OrigenAlias.APRENDIDO, estado=EstadoAlias.PROPUESTO)
        nuevo.version = 1
        nuevo.historial = [_evento(nuevo, "aprendizaje")]
        db.add(nuevo)
        await db.flush()
        return nuevo
    if existente.estado is EstadoAlias.ACTIVO:
        if existente.series_id == series_id:
            return existente
        existente.historial = [
            *(existente.historial or []),
            _evento(existente, "conflicto", series_propuesta=str(series_id)),
        ]
        await db.flush()
        return existente
    if existente.estado is EstadoAlias.RETIRADO:
        motivo = "reactivacion_por_aprendizaje"
    else:
        motivo = "aprendizaje"
    existente.series_id = series_id
    existente.estado = EstadoAlias.PROPUESTO
    existente.origen = existente.origen or OrigenAlias.APRENDIDO
    existente.version = (existente.version or 0) + 1
    existente.actualizado_en = _ahora()
    existente.historial = [*(existente.historial or []), _evento(existente, motivo)]
    await db.flush()
    return existente


async def activar_local(db: AsyncSession, alias_id: UUID, *, confirmado: bool) -> LocalAlias:
    _exigir_confirmacion(confirmado)
    alias = await _local(db, alias_id)
    if alias.estado is EstadoAlias.RETIRADO:
        raise TransicionInvalidaError("Un alias retirado no se reactiva; el historial se conserva.")
    if alias.estado is EstadoAlias.ACTIVO:
        return alias
    _aplicar(alias, EstadoAlias.ACTIVO, "activacion")
    await db.commit()
    await db.refresh(alias)
    return alias


async def desactivar_local(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    alias = await _local(db, alias_id)
    if alias.estado is EstadoAlias.RETIRADO:
        raise TransicionInvalidaError("Un alias retirado no se puede desactivar.")
    if alias.estado is EstadoAlias.DESACTIVADO:
        return alias
    _aplicar(alias, EstadoAlias.DESACTIVADO, "desactivacion")
    await db.commit()
    await db.refresh(alias)
    return alias


async def reactivar_local(db: AsyncSession, alias_id: UUID, *,
                          confirmado: bool) -> LocalAlias:
    _exigir_confirmacion(confirmado)
    alias = await _local(db, alias_id)
    if alias.estado is EstadoAlias.RETIRADO:
        raise TransicionInvalidaError("Un alias retirado no se reactiva; el historial se conserva.")
    if alias.estado is EstadoAlias.ACTIVO:
        return alias
    _aplicar(alias, EstadoAlias.ACTIVO, "reactivacion")
    await db.commit()
    await db.refresh(alias)
    return alias


async def retirar_local(db: AsyncSession, alias_id: UUID) -> LocalAlias:
    alias = await _local(db, alias_id)
    if alias.estado is EstadoAlias.RETIRADO:
        return alias                      # idempotente: no duplica versión ni historial
    _aplicar(alias, EstadoAlias.RETIRADO, "retirada")
    await db.commit()
    await db.refresh(alias)
    return alias


async def listar_aprendidos(db: AsyncSession, *, estado: EstadoAlias | None = None,
                            incluir_historial: bool = False) -> list[LocalAlias]:
    consulta = select(LocalAlias)
    if estado is not None:
        consulta = consulta.where(LocalAlias.estado == estado)
    return list((await db.execute(
        consulta.order_by(LocalAlias.pattern_norm))).scalars().all())


# ── Alias de importación (versionado por filas) ──────────────────────────────

async def _importado_vigente(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    actual = (await db.execute(
        select(AliasImportado)
        .where(AliasImportado.alias_id == alias_id,
               AliasImportado.vigente_hasta.is_(None))
    )).scalar_one_or_none()
    if actual is None:
        raise AliasNoEncontradoError("Ese alias importado ya no existe.")
    return actual


async def _nueva_version_importada(db: AsyncSession, actual: AliasImportado,
                                   estado: EstadoAlias) -> AliasImportado:
    momento = _ahora()
    actual.vigente_hasta = momento
    nueva = AliasImportado(
        id=uuid4(), alias_id=actual.alias_id, version=actual.version + 1,
        patron_norm=actual.patron_norm, scope_path=actual.scope_path,
        series_id=actual.series_id, origen=actual.origen, estado=estado,
        vigente_desde=momento, procedencia=dict(actual.procedencia or {}))
    db.add(nueva)
    await db.commit()
    await db.refresh(nueva)
    return nueva


async def activar_importado(db: AsyncSession, alias_id: UUID, *,
                            confirmado: bool) -> AliasImportado:
    _exigir_confirmacion(confirmado)
    actual = await _importado_vigente(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        raise TransicionInvalidaError("Un alias retirado no se reactiva; el historial se conserva.")
    if actual.estado is EstadoAlias.ACTIVO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.ACTIVO)


async def desactivar_importado(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    actual = await _importado_vigente(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        raise TransicionInvalidaError("Un alias retirado no se puede desactivar.")
    if actual.estado is EstadoAlias.DESACTIVADO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.DESACTIVADO)


async def reactivar_importado(db: AsyncSession, alias_id: UUID, *,
                              confirmado: bool) -> AliasImportado:
    _exigir_confirmacion(confirmado)
    actual = await _importado_vigente(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        raise TransicionInvalidaError("Un alias retirado no se reactiva; el historial se conserva.")
    if actual.estado is EstadoAlias.ACTIVO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.ACTIVO)


async def retirar_importado(db: AsyncSession, alias_id: UUID) -> AliasImportado:
    actual = await _importado_vigente(db, alias_id)
    if actual.estado is EstadoAlias.RETIRADO:
        return actual
    return await _nueva_version_importada(db, actual, EstadoAlias.RETIRADO)


async def listar_importados(db: AsyncSession, *, estado: EstadoAlias | None = None,
                            incluir_historial: bool = False) -> list[AliasImportado]:
    consulta = select(AliasImportado)
    if not incluir_historial:
        consulta = consulta.where(AliasImportado.vigente_hasta.is_(None))
    if estado is not None:
        consulta = consulta.where(AliasImportado.estado == estado)
    return list((await db.execute(
        consulta.order_by(AliasImportado.patron_norm,
                          AliasImportado.version))).scalars().all())
