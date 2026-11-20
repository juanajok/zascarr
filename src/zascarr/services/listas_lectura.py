"""#1080: listas de lectura curadas de números concretos.

Independientes de Colecciones (series) y Sagas. No son cola de lectura ni
alimentan el «siguiente» del lector en esta historia.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    Issue,
    ReadingList,
    ReadingListItem,
    ReadingProgress,
    ReadingStatus,
    Series,
)

NOMBRE_MAX = 120
DESCRIPCION_MAX = 2000


class ListaInvalidaError(ValueError):
    """Error de validación con mensaje para el coleccionista."""


@dataclass(frozen=True)
class ListaResumen:
    id: str
    nombre: str
    descripcion: str | None
    total: int
    leidos: int


@dataclass(frozen=True)
class ItemLista:
    issue_id: str
    numero: str
    titulo: str | None
    serie: str
    serie_id: str
    position: int
    leido: bool


def _nombre(valor: str) -> str:
    limpio = " ".join((valor or "").split())
    if not limpio:
        raise ListaInvalidaError("El nombre de la lista no puede estar vacío.")
    if len(limpio) > NOMBRE_MAX:
        raise ListaInvalidaError(f"El nombre no puede pasar de {NOMBRE_MAX} caracteres.")
    return limpio


def _descripcion(valor: str | None) -> str | None:
    limpio = " ".join((valor or "").split())
    if len(limpio) > DESCRIPCION_MAX:
        raise ListaInvalidaError(f"La descripción no puede pasar de {DESCRIPCION_MAX} caracteres.")
    return limpio or None


async def listar(db: AsyncSession) -> list[ListaResumen]:
    filas = (await db.execute(
        select(ReadingList.id, ReadingList.name, ReadingList.description,
               func.count(ReadingListItem.issue_id),
               func.count(ReadingProgress.id).filter(
                   ReadingProgress.status == ReadingStatus.COMPLETED))
        .outerjoin(ReadingListItem, ReadingListItem.reading_list_id == ReadingList.id)
        .outerjoin(ReadingProgress, ReadingProgress.issue_id == ReadingListItem.issue_id)
        .group_by(ReadingList.id, ReadingList.name, ReadingList.description)
        .order_by(ReadingList.name, ReadingList.id)
    )).all()
    return [ListaResumen(str(i), n, d, int(t), int(leidos)) for i, n, d, t, leidos in filas]


async def detalle(db: AsyncSession, lista_id: UUID) -> dict | None:
    lista = await db.get(ReadingList, lista_id)
    if lista is None:
        return None
    filas = (await db.execute(
        select(ReadingListItem, Issue, Series, ReadingProgress)
        .join(Issue, Issue.id == ReadingListItem.issue_id)
        .join(Series, Series.id == Issue.series_id)
        .outerjoin(ReadingProgress, ReadingProgress.issue_id == Issue.id)
        .where(ReadingListItem.reading_list_id == lista_id)
        .order_by(ReadingListItem.position, Issue.issue_number)
    )).all()
    items = [ItemLista(
        str(r.issue_id), i.issue_number or "", i.title, s.title, str(s.id), r.position,
        p is not None and p.status is ReadingStatus.COMPLETED)
        for r, i, s, p in filas]
    return {"lista": lista, "items": items,
            "total": len(items), "leidos": sum(1 for x in items if x.leido)}


async def crear(db: AsyncSession, nombre: str, descripcion: str = "") -> ReadingList:
    lista = ReadingList(name=_nombre(nombre), description=_descripcion(descripcion))
    db.add(lista)
    await db.flush()
    return lista


async def renombrar(db: AsyncSession, lista_id: UUID, nombre: str,
                    descripcion: str = "") -> None:
    lista = await db.get(ReadingList, lista_id)
    if lista is None:
        raise ListaInvalidaError("La lista ya no existe.")
    lista.name = _nombre(nombre)
    lista.description = _descripcion(descripcion)
    await db.flush()


async def borrar(db: AsyncSession, lista_id: UUID) -> None:
    lista = await db.get(ReadingList, lista_id)
    if lista is not None:
        await db.delete(lista)
        await db.flush()


async def anadir(db: AsyncSession, lista_id: UUID, issue_id: UUID) -> None:
    if await db.get(ReadingList, lista_id) is None:
        raise ListaInvalidaError("La lista ya no existe.")
    if await db.get(Issue, issue_id) is None:
        raise ListaInvalidaError("Ese número no existe.")
    existe = (await db.execute(select(ReadingListItem).where(
        ReadingListItem.reading_list_id == lista_id,
        ReadingListItem.issue_id == issue_id))).scalar_one_or_none()
    if existe is not None:
        raise ListaInvalidaError("Ese número ya está en la lista.")
    maxima = (await db.execute(
        select(func.max(ReadingListItem.position)).where(
            ReadingListItem.reading_list_id == lista_id))).scalar() or 0
    db.add(ReadingListItem(reading_list_id=lista_id, issue_id=issue_id,
                           position=int(maxima) + 1))
    await db.flush()


async def quitar(db: AsyncSession, lista_id: UUID, issue_id: UUID) -> None:
    await db.execute(delete(ReadingListItem).where(
        ReadingListItem.reading_list_id == lista_id,
        ReadingListItem.issue_id == issue_id))
    await _compactar(db, lista_id)


async def mover(db: AsyncSession, lista_id: UUID, issue_id: UUID, direccion: str) -> bool:
    filas = list((await db.execute(
        select(ReadingListItem).where(ReadingListItem.reading_list_id == lista_id)
        .order_by(ReadingListItem.position))).scalars().all())
    indice = next((i for i, f in enumerate(filas) if str(f.issue_id) == str(issue_id)), None)
    if indice is None:
        return False
    destino = indice - 1 if direccion == "subir" else indice + 1
    if destino < 0 or destino >= len(filas):
        return False
    for i, fila in enumerate(filas, 1):
        fila.position = i
    filas[indice].position, filas[destino].position = (
        filas[destino].position, filas[indice].position)
    await db.flush()
    return True


async def _compactar(db: AsyncSession, lista_id: UUID) -> None:
    filas = list((await db.execute(
        select(ReadingListItem).where(ReadingListItem.reading_list_id == lista_id)
        .order_by(ReadingListItem.position))).scalars().all())
    for i, fila in enumerate(filas, 1):
        fila.position = i
    await db.flush()
