"""BL-C4 (#151): arcos/sagas en orden de lectura, aunque crucen series.

Solo lectura sobre `story_arcs` y `story_arc_issues.reading_order`. No crea ni
modifica arcos, no consulta fuentes y no toca archivos.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    File,
    Issue,
    Series,
    StoryArc,
    StoryArcIssue,
    Wishlist,
    WishlistOrigin,
    WishlistStatus,
)

POR_PAGINA = 50


@dataclass(frozen=True)
class ArcoResumen:
    id: str
    title: str
    is_crossover: bool
    numeros: int
    series: int


@dataclass(frozen=True)
class FilaArco:
    orden: int
    issue_id: str
    series_id: str
    series: str
    numero: str
    titulo: str | None
    fecha: str | None
    disponible: bool


@dataclass(frozen=True)
class PaginaArcos:
    filas: list[ArcoResumen]
    total: int
    pagina: int
    paginas: int
    desde: int
    hasta: int


@dataclass(frozen=True)
class DetalleArco:
    id: str
    title: str
    description: str | None
    is_crossover: bool
    filas: list[FilaArco]
    series: int


async def listar_arcos(db: AsyncSession, pagina: int = 1) -> PaginaArcos:
    total = (await db.execute(
        select(func.count()).select_from(StoryArc))).scalar_one()
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    desde = (pagina - 1) * POR_PAGINA
    filas = (await db.execute(
        select(
            StoryArc.id, StoryArc.title, StoryArc.is_crossover,
            func.count(StoryArcIssue.issue_id).label("numeros"),
            func.count(func.distinct(Issue.series_id)).label("series"),
        )
        .outerjoin(StoryArcIssue, StoryArcIssue.story_arc_id == StoryArc.id)
        .outerjoin(Issue, Issue.id == StoryArcIssue.issue_id)
        .group_by(StoryArc.id, StoryArc.title, StoryArc.is_crossover)
        .order_by(StoryArc.title, StoryArc.id)
        .offset(desde).limit(POR_PAGINA))).all()
    return PaginaArcos(
        filas=[ArcoResumen(str(f.id), f.title, bool(f.is_crossover),
                           int(f.numeros or 0), int(f.series or 0)) for f in filas],
        total=total, pagina=pagina, paginas=paginas, desde=desde,
        hasta=min(desde + POR_PAGINA, total))


async def detalle_arco(db: AsyncSession, arco_id: UUID) -> DetalleArco | None:
    arco = (await db.execute(
        select(StoryArc).where(StoryArc.id == arco_id))).scalar_one_or_none()
    if arco is None:
        return None
    filas = (await db.execute(
        select(
            StoryArcIssue.reading_order, Issue.id.label("issue_id"),
            Issue.issue_number, Issue.title.label("issue_title"),
            Issue.release_date, Series.id.label("series_id"),
            Series.title.label("series_title"),
            exists().where(File.issue_id == Issue.id,
                           File.is_missing.is_(False)).label("disponible"),
        )
        .join(Issue, Issue.id == StoryArcIssue.issue_id)
        .join(Series, Series.id == Issue.series_id)
        .where(StoryArcIssue.story_arc_id == arco_id)
        .order_by(StoryArcIssue.reading_order, Series.title, Issue.issue_number)
    )).all()
    detalle = [
        FilaArco(
            orden=int(f.reading_order), issue_id=str(f.issue_id),
            series_id=str(f.series_id), series=f.series_title,
            numero=f.issue_number or "Sin número", titulo=f.issue_title,
            fecha=f.release_date.isoformat() if f.release_date else None,
            disponible=bool(f.disponible))
        for f in filas
    ]
    return DetalleArco(
        id=str(arco.id), title=arco.title, description=arco.description,
        is_crossover=bool(arco.is_crossover), filas=detalle,
        series=len({f.series_id for f in detalle}))


@dataclass
class ResultadoPedidoArco:
    """BL-D7: resultado de pedir de una vez los números de una saga."""
    ok: bool
    errores: dict[str, str] = field(default_factory=dict)
    anadidos: int = 0
    ya_pedidos: int = 0
    en_biblioteca: int = 0
    total: int = 0


async def pedir_arco(db: AsyncSession, arco_id: UUID) -> ResultadoPedidoArco:
    """BL-D7: añade al wishlist los números de la saga que falten.

    No crea una tabla nueva: un deseo por `issue` es suficiente y el orden se
    conserva en `StoryArcIssue.reading_order` y en la prioridad del deseo. Los
    deseos son manuales: la retirada automática de la política de una serie no
    los toca. Los que ya están pedidos (incluidos los retirados) se omiten.
    """
    arco = await db.get(StoryArc, arco_id)
    if arco is None:
        return ResultadoPedidoArco(False, {"general": "La saga ya no existe."})
    filas = (await db.execute(
        select(StoryArcIssue.issue_id, StoryArcIssue.reading_order)
        .where(StoryArcIssue.story_arc_id == arco_id)
        .order_by(StoryArcIssue.reading_order, StoryArcIssue.issue_id)
    )).all()
    if not filas:
        return ResultadoPedidoArco(False, {"general": "La saga no tiene números."})
    pedidos = set((await db.execute(
        select(Wishlist.issue_id).where(
            Wishlist.issue_id.is_not(None),
            Wishlist.status != WishlistStatus.RETIRADO,
        ))).scalars().all())
    en_biblioteca = set((await db.execute(
        select(File.issue_id).where(
            File.issue_id.in_([f.issue_id for f in filas]),
            File.is_missing.is_(False),
        ))).scalars().all())
    anadidos = ya = biblioteca = 0
    for fila in filas:
        if fila.issue_id in en_biblioteca:
            biblioteca += 1
        elif fila.issue_id in pedidos:
            ya += 1
        else:
            db.add(Wishlist(
                issue_id=fila.issue_id, origen=WishlistOrigin.MANUAL,
                priority=int(fila.reading_order) or 1,
                notes=f"Saga: {arco.title}"))
            anadidos += 1
    await db.flush()
    return ResultadoPedidoArco(True, anadidos=anadidos, ya_pedidos=ya,
                               en_biblioteca=biblioteca, total=len(filas))


@dataclass
class ResultadoArco:
    ok: bool
    errores: dict[str, str] = field(default_factory=dict)
    arco: StoryArc | None = None


def _titulo(valor: str) -> tuple[str, str | None]:
    titulo = (valor or "").strip()
    if not titulo:
        return "", "El título no puede estar vacío."
    if len(titulo) > 500:
        return "", "El título no puede superar 500 caracteres."
    return titulo, None


async def crear_arco(db: AsyncSession, *, title: str, description: str,
                     is_crossover: bool) -> ResultadoArco:
    titulo, error = _titulo(title)
    errores = {}
    if error:
        errores["title"] = error
    descripcion = (description or "").strip()
    if len(descripcion) > 10_000:
        errores["description"] = "La descripción no puede superar 10000 caracteres."
    if errores:
        return ResultadoArco(False, errores)
    arco = StoryArc(title=titulo, description=descripcion or None,
                    is_crossover=bool(is_crossover))
    db.add(arco)
    await db.flush()
    return ResultadoArco(True, arco=arco)


async def editar_arco(db: AsyncSession, arco_id: UUID, *, title: str,
                      description: str, is_crossover: bool) -> ResultadoArco:
    arco = await db.get(StoryArc, arco_id)
    if arco is None:
        return ResultadoArco(False, {"general": "La saga ya no existe."})
    titulo, error = _titulo(title)
    errores = {}
    if error:
        errores["title"] = error
    descripcion = (description or "").strip()
    if len(descripcion) > 10_000:
        errores["description"] = "La descripción no puede superar 10000 caracteres."
    if errores:
        return ResultadoArco(False, errores, arco)
    arco.title = titulo
    arco.description = descripcion or None
    arco.is_crossover = bool(is_crossover)
    await db.flush()
    return ResultadoArco(True, arco=arco)


async def eliminar_arco(db: AsyncSession, arco_id: UUID) -> bool:
    arco = await db.get(StoryArc, arco_id)
    if arco is None:
        return False
    await db.delete(arco)      # cascade de story_arc_issues; no toca issues/files
    await db.flush()
    return True


async def _serie_por_texto(db: AsyncSession, texto: str) -> Series | None:
    """Una serie por id (UUID) o por título exacto; ambigüedad → None (se avisa)."""
    texto = (texto or "").strip()
    if not texto:
        return None
    try:
        return await db.get(Series, UUID(texto))
    except (ValueError, TypeError):
        pass
    filas = (await db.execute(
        select(Series).where(func.lower(Series.title) == texto.casefold())
        .order_by(Series.start_year, Series.id).limit(2))).scalars().all()
    return filas[0] if len(filas) == 1 else None


async def agregar_numero(db: AsyncSession, arco_id: UUID, *, serie: str,
                         numero: str, orden: int | None = None) -> ResultadoArco:
    arco = await db.get(StoryArc, arco_id)
    if arco is None:
        return ResultadoArco(False, {"general": "La saga ya no existe."})
    numero = (numero or "").strip()
    if not numero:
        return ResultadoArco(False, {"numero": "Escribe el número."})
    serie_obj = await _serie_por_texto(db, serie)
    if serie_obj is None:
        return ResultadoArco(False, {
            "serie": "No encuentro una única serie con ese nombre. Escribe el título exacto."})
    issue = (await db.execute(select(Issue).where(
        Issue.series_id == serie_obj.id, Issue.issue_number == numero))).scalar_one_or_none()
    if issue is None:
        return ResultadoArco(False, {
            "numero": f"No existe el nº {numero} en «{serie_obj.title}»."})
    existente = (await db.execute(select(StoryArcIssue).where(
        StoryArcIssue.story_arc_id == arco_id,
        StoryArcIssue.issue_id == issue.id))).scalar_one_or_none()
    if existente is not None:
        return ResultadoArco(False, {"numero": "Ese número ya está en la saga."})
    maximo = (await db.execute(
        select(func.max(StoryArcIssue.reading_order)).where(
            StoryArcIssue.story_arc_id == arco_id))).scalar_one() or 0
    posicion = max(1, min(int(orden) if orden is not None else maximo + 1, maximo + 1))
    if posicion <= maximo:
        await db.execute(
            StoryArcIssue.__table__.update()
            .where(StoryArcIssue.story_arc_id == arco_id,
                   StoryArcIssue.reading_order >= posicion)
            .values(reading_order=StoryArcIssue.reading_order + 1))
    db.add(StoryArcIssue(story_arc_id=arco_id, issue_id=issue.id, reading_order=posicion))
    await db.flush()
    return ResultadoArco(True, arco=arco)


async def quitar_numero(db: AsyncSession, arco_id: UUID, issue_id: UUID) -> bool:
    vinculo = await db.get(StoryArcIssue, (arco_id, issue_id))
    if vinculo is None:
        return False
    await db.delete(vinculo)
    await db.flush()
    filas = (await db.execute(
        select(StoryArcIssue).where(StoryArcIssue.story_arc_id == arco_id)
        .order_by(StoryArcIssue.reading_order))).scalars().all()
    for posicion, fila in enumerate(filas, start=1):
        fila.reading_order = posicion
    await db.flush()
    return True


async def mover_numero(db: AsyncSession, arco_id: UUID, issue_id: UUID, *, subir: bool) -> bool:
    filas = (await db.execute(
        select(StoryArcIssue).where(StoryArcIssue.story_arc_id == arco_id)
        .order_by(StoryArcIssue.reading_order))).scalars().all()
    indice = next((i for i, f in enumerate(filas) if f.issue_id == issue_id), None)
    if indice is None:
        return False
    destino = indice - 1 if subir else indice + 1
    if destino < 0 or destino >= len(filas):
        return True
    filas[indice].reading_order, filas[destino].reading_order = (
        filas[destino].reading_order, filas[indice].reading_order)
    await db.flush()
    return True
