# ruff: noqa: E501
"""MIT-M7 (#130-a): declarar el significado de una carpeta.

Solo filas de `declaraciones_carpeta`: no lee ni escribe archivos, no crea
series/publicaciones, no vincula nada y no reejecuta decisiones. Cada cambio
semántico o de ciclo inserta una versión nueva y cierra la anterior.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    DeclaracionCarpeta,
    EstadoRegla,
    OrigenRegla,
    TipoSignificadoCarpeta,
)

MAX_RUTA = 2000
_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


class DeclaracionError(Exception):
    """Error de negocio con mensaje ya en español para la superficie."""


class RutaInvalidaError(DeclaracionError):
    pass


class TipoInvalidoError(DeclaracionError):
    pass


class OrigenInvalidoError(DeclaracionError):
    pass


class DeclaracionNoEncontradaError(DeclaracionError):
    pass


class DeclaracionRetiradaError(DeclaracionError):
    pass


class DeclaracionDuplicadaError(DeclaracionError):
    pass


class EstadoInvalidoError(DeclaracionError):
    pass


def normalizar_ruta(contexto_raiz: str, *, raiz_biblioteca: str | Path | None = None) -> str:
    """Ruta relativa normalizada: NFC, `/`, sin `.`/`..`, sin barra final.

    Rechaza rutas absolutas, vacías, la raíz de la biblioteca y cualquier
    intento de escapar de ella. Distingue mayúsculas.
    """
    if raiz_biblioteca is not None:
        raiz = str(raiz_biblioteca).replace("\\", "/").strip().rstrip("/")
        candidata = contexto_raiz.replace("\\", "/").strip().rstrip("/")
        if candidata == raiz:
            raise RutaInvalidaError("No se puede declarar la raíz de la biblioteca.")
    if not contexto_raiz or not contexto_raiz.strip():
        raise RutaInvalidaError("La carpeta no puede estar vacía.")
    bruta = unicodedata.normalize("NFC", contexto_raiz.strip())
    if bruta.startswith(("/", "\\")) or _DRIVE.match(bruta):
        raise RutaInvalidaError("La carpeta debe ser una ruta relativa dentro de la biblioteca.")
    partes = [p for p in bruta.replace("\\", "/").split("/") if p not in ("", ".")]
    if not partes or any(p == ".." for p in partes):
        raise RutaInvalidaError("La carpeta no puede salir de la biblioteca.")
    ruta = "/".join(partes)
    if len(ruta) > MAX_RUTA:
        raise RutaInvalidaError("La ruta de la carpeta es demasiado larga.")
    return ruta


def _tipo(valor: TipoSignificadoCarpeta | str) -> TipoSignificadoCarpeta:
    try:
        return TipoSignificadoCarpeta(valor)
    except (TypeError, ValueError):
        raise TipoInvalidoError(
            "El tipo de carpeta solo puede ser «autor» o «publicación».") from None


def _origen(valor: OrigenRegla | str) -> OrigenRegla:
    try:
        return OrigenRegla(valor)
    except (TypeError, ValueError):
        raise OrigenInvalidoError(
            "El origen solo puede ser local o importación.") from None


def _ahora(ahora: datetime | None) -> datetime:
    return ahora or datetime.now(UTC)


@dataclass(frozen=True)
class DeclaracionVista:
    id: UUID
    declaracion_id: UUID
    version: int
    contexto_raiz: str
    incluir_descendientes: bool
    tipo_de_significado: TipoSignificadoCarpeta
    origen: OrigenRegla
    estado: EstadoRegla
    vigente_desde: datetime
    vigente_hasta: datetime | None
    procedencia: dict

    @property
    def alcance(self) -> str:
        return ("Esta carpeta y sus subcarpetas" if self.incluir_descendientes
                else "Solo esta carpeta")

    @property
    def efectos(self) -> str:
        return ("Solo orienta: no crea series ni publicaciones, no vincula archivos, "
                "no los mueve ni los renombra.")

    @classmethod
    def de(cls, fila: DeclaracionCarpeta) -> DeclaracionVista:
        return cls(
            id=fila.id, declaracion_id=fila.declaracion_id, version=fila.version,
            contexto_raiz=fila.contexto_raiz,
            incluir_descendientes=fila.incluir_descendientes,
            tipo_de_significado=fila.tipo_de_significado, origen=fila.origen,
            estado=fila.estado, vigente_desde=fila.vigente_desde,
            vigente_hasta=fila.vigente_hasta, procedencia=dict(fila.procedencia or {}),
        )


def _fila_nueva(actual: DeclaracionCarpeta | None, *, declaracion_id: UUID, version: int,
                contexto_raiz: str, incluir: bool, tipo: TipoSignificadoCarpeta,
                origen: OrigenRegla, estado: EstadoRegla, ahora: datetime,
                procedencia: dict) -> DeclaracionCarpeta:
    return DeclaracionCarpeta(
        id=uuid4(), declaracion_id=declaracion_id, version=version,
        contexto_raiz=contexto_raiz, incluir_descendientes=incluir,
        tipo_de_significado=tipo, origen=origen, estado=estado,
        vigente_desde=ahora, vigente_hasta=None, procedencia=procedencia,
    )


async def _vigente_por_identidad(db: AsyncSession, declaracion_id: UUID) -> DeclaracionCarpeta:
    fila = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.declaracion_id == declaracion_id,
            DeclaracionCarpeta.vigente_hasta.is_(None))
        .with_for_update())).scalar_one_or_none()
    if fila is None:
        raise DeclaracionNoEncontradaError("No encontramos esa declaración de carpeta.")
    return fila


async def declarar(db: AsyncSession, contexto_raiz: str, *,
                   tipo_de_significado: TipoSignificadoCarpeta | str,
                   incluir_descendientes: bool = False,
                   origen: OrigenRegla | str = OrigenRegla.LOCAL,
                   procedencia: dict | None = None,
                   raiz_biblioteca: str | Path | None = None,
                   ahora: datetime | None = None) -> DeclaracionVista:
    ruta = normalizar_ruta(contexto_raiz, raiz_biblioteca=raiz_biblioteca)
    tipo = _tipo(tipo_de_significado)
    origen_enum = _origen(origen)
    if origen_enum is OrigenRegla.LOCAL:
        activa = (await db.execute(
            select(DeclaracionCarpeta.id).where(
                DeclaracionCarpeta.contexto_raiz == ruta,
                DeclaracionCarpeta.vigente_hasta.is_(None),
                DeclaracionCarpeta.origen == OrigenRegla.LOCAL,
                DeclaracionCarpeta.estado == EstadoRegla.ACTIVA))).scalar_one_or_none()
        if activa is not None:
            raise DeclaracionDuplicadaError(
                "Ya hay una declaración activa para esa carpeta; cámbiala o desactívala.")
    fila = _fila_nueva(None, declaracion_id=uuid4(), version=1, contexto_raiz=ruta,
                       incluir=bool(incluir_descendientes), tipo=tipo, origen=origen_enum,
                       estado=EstadoRegla.ACTIVA, ahora=_ahora(ahora),
                       procedencia=dict(procedencia or {}))
    db.add(fila)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DeclaracionDuplicadaError(
            "Ya hay una declaración activa para esa carpeta; cámbiala o desactívala.") from exc
    await db.refresh(fila)
    return DeclaracionVista.de(fila)


async def cambiar(db: AsyncSession, declaracion_id: UUID, *,
                  tipo_de_significado: TipoSignificadoCarpeta | str | None = None,
                  incluir_descendientes: bool | None = None,
                  procedencia: dict | None = None,
                  ahora: datetime | None = None) -> DeclaracionVista:
    actual = await _vigente_por_identidad(db, declaracion_id)
    if actual.estado is EstadoRegla.RETIRADA:
        raise DeclaracionRetiradaError("Una declaración retirada no se puede cambiar.")
    tipo = _tipo(tipo_de_significado) if tipo_de_significado is not None else actual.tipo_de_significado
    incluir = bool(incluir_descendientes) if incluir_descendientes is not None else actual.incluir_descendientes
    if tipo is actual.tipo_de_significado and incluir == actual.incluir_descendientes:
        return DeclaracionVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    nueva = _fila_nueva(actual, declaracion_id=actual.declaracion_id,
                        version=actual.version + 1, contexto_raiz=actual.contexto_raiz,
                        incluir=incluir, tipo=tipo, origen=actual.origen,
                        estado=actual.estado if actual.estado is not EstadoRegla.RETIRADA
                        else EstadoRegla.DESACTIVADA,
                        ahora=momento,
                        procedencia=dict(procedencia if procedencia is not None else actual.procedencia or {}))
    db.add(nueva)
    await db.commit()
    await db.refresh(nueva)
    return DeclaracionVista.de(nueva)


async def desactivar(db: AsyncSession, declaracion_id: UUID, *, ahora: datetime | None = None) -> DeclaracionVista:
    actual = await _vigente_por_identidad(db, declaracion_id)
    if actual.estado is EstadoRegla.RETIRADA:
        raise DeclaracionRetiradaError("Una declaración retirada no se puede desactivar.")
    if actual.estado is EstadoRegla.DESACTIVADA:
        return DeclaracionVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    nueva = _fila_nueva(actual, declaracion_id=actual.declaracion_id,
                        version=actual.version + 1, contexto_raiz=actual.contexto_raiz,
                        incluir=actual.incluir_descendientes,
                        tipo=actual.tipo_de_significado, origen=actual.origen,
                        estado=EstadoRegla.DESACTIVADA, ahora=momento,
                        procedencia=dict(actual.procedencia or {}))
    db.add(nueva)
    await db.commit()
    await db.refresh(nueva)
    return DeclaracionVista.de(nueva)


async def reactivar(db: AsyncSession, declaracion_id: UUID, *, ahora: datetime | None = None) -> DeclaracionVista:
    actual = await _vigente_por_identidad(db, declaracion_id)
    if actual.estado is EstadoRegla.RETIRADA:
        raise DeclaracionRetiradaError(
            "Una declaración retirada no se reactiva; crea una declaración nueva.")
    if actual.estado is EstadoRegla.ACTIVA:
        return DeclaracionVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    nueva = _fila_nueva(actual, declaracion_id=actual.declaracion_id,
                        version=actual.version + 1, contexto_raiz=actual.contexto_raiz,
                        incluir=actual.incluir_descendientes,
                        tipo=actual.tipo_de_significado, origen=actual.origen,
                        estado=EstadoRegla.ACTIVA, ahora=momento,
                        procedencia=dict(actual.procedencia or {}))
    db.add(nueva)
    await db.commit()
    await db.refresh(nueva)
    return DeclaracionVista.de(nueva)


async def retirar(db: AsyncSession, declaracion_id: UUID, *, ahora: datetime | None = None) -> DeclaracionVista:
    actual = await _vigente_por_identidad(db, declaracion_id)
    if actual.estado is EstadoRegla.RETIRADA:
        return DeclaracionVista.de(actual)
    momento = _ahora(ahora)
    actual.vigente_hasta = momento
    nueva = _fila_nueva(actual, declaracion_id=actual.declaracion_id,
                        version=actual.version + 1, contexto_raiz=actual.contexto_raiz,
                        incluir=actual.incluir_descendientes,
                        tipo=actual.tipo_de_significado, origen=actual.origen,
                        estado=EstadoRegla.RETIRADA, ahora=momento,
                        procedencia=dict(actual.procedencia or {}))
    db.add(nueva)
    await db.commit()
    await db.refresh(nueva)
    return DeclaracionVista.de(nueva)


async def listar(db: AsyncSession, *, tipo: TipoSignificadoCarpeta | str | None = None,
                 origen: OrigenRegla | str | None = None,
                 estado: EstadoRegla | str | None = None,
                 incluir_historial: bool = False) -> list[DeclaracionVista]:
    consulta = select(DeclaracionCarpeta)
    if not incluir_historial:
        consulta = consulta.where(DeclaracionCarpeta.vigente_hasta.is_(None))
    if tipo is not None:
        consulta = consulta.where(DeclaracionCarpeta.tipo_de_significado == _tipo(tipo))
    if origen is not None:
        consulta = consulta.where(DeclaracionCarpeta.origen == _origen(origen))
    if estado is not None:
        try:
            estado_enum = EstadoRegla(estado)
        except (TypeError, ValueError):
            raise EstadoInvalidoError(
                "El estado solo puede ser activa, desactivada o retirada.") from None
        consulta = consulta.where(DeclaracionCarpeta.estado == estado_enum)
    consulta = consulta.order_by(DeclaracionCarpeta.contexto_raiz,
                                 DeclaracionCarpeta.declaracion_id,
                                 DeclaracionCarpeta.version)
    filas = (await db.execute(consulta)).scalars().all()
    return [DeclaracionVista.de(f) for f in filas]


async def historial(db: AsyncSession, declaracion_id: UUID) -> list[DeclaracionVista]:
    filas = (await db.execute(
        select(DeclaracionCarpeta)
        .where(DeclaracionCarpeta.declaracion_id == declaracion_id)
        .order_by(DeclaracionCarpeta.version))).scalars().all()
    return [DeclaracionVista.de(f) for f in filas]


async def vigente(db: AsyncSession, contexto_raiz: str, *,
                  raiz_biblioteca: str | Path | None = None) -> DeclaracionVista | None:
    ruta = normalizar_ruta(contexto_raiz, raiz_biblioteca=raiz_biblioteca)
    filas = (await db.execute(
        select(DeclaracionCarpeta).where(
            DeclaracionCarpeta.contexto_raiz == ruta,
            DeclaracionCarpeta.vigente_hasta.is_(None),
            DeclaracionCarpeta.estado == EstadoRegla.ACTIVA)
        .order_by(DeclaracionCarpeta.origen))).scalars().all()
    if not filas:
        return None
    local = [f for f in filas if f.origen is OrigenRegla.LOCAL]
    return DeclaracionVista.de((local or filas)[0])
