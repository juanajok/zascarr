"""#155/BL-D6: colecciones de series y su política de auto-búsqueda.

Una serie pertenece como máximo a una colección. La colección no cambia la
política guardada de la serie (la ficha puede seguir mostrándola), solo decide
la **política efectiva** con la que el orquestador genera/retira items.
Sin fuentes, calidad ni ficheros: esta historia es solo agrupación y política.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import Collection, CollectionAutoSearch, ComicTradition, Series, WishlistPolicy
from zascarr.services.portada_coleccion import VERSION as PORTADA_VERSION
from zascarr.services.portada_coleccion import portada_cacheada

MAX_NOMBRE = 120
MAX_DESCRIPCION = 500


@dataclass(frozen=True)
class ColeccionResumen:
    id: str
    name: str
    description: str | None
    auto_search: str
    series: int
    tiene_portada: bool = False
    portada_url: str = ""


ETIQUETAS_POLITICA = {
    WishlistPolicy.NONE.value: "No buscar automáticamente",
    WishlistPolicy.MISSING.value: "Buscar los números que faltan",
    WishlistPolicy.FUTURE.value: "Números futuros (todavía no disponible)",
    WishlistPolicy.ALL.value: "Todos los números (reservado)",
}


def etiqueta_politica(valor: str | WishlistPolicy | None) -> str:
    crudo = (valor.value if isinstance(valor, WishlistPolicy)
             else (valor or WishlistPolicy.NONE.value))
    return ETIQUETAS_POLITICA.get(crudo, "No buscar automáticamente")


def politica_efectiva_de(guardada: str | WishlistPolicy | None,
                         auto_search: str | CollectionAutoSearch | None) -> str:
    """Misma regla que `politica_efectiva` pero sin BD, para los DTO de la UI."""
    crudo = guardada.value if isinstance(guardada, WishlistPolicy) else (guardada or "ninguno")
    auto = auto_search.value if isinstance(auto_search, CollectionAutoSearch) else auto_search
    if auto == CollectionAutoSearch.INCLUIR.value:
        return WishlistPolicy.MISSING.value
    if auto == CollectionAutoSearch.EXCLUIR.value:
        return WishlistPolicy.NONE.value
    return crudo


@dataclass(frozen=True)
class SerieDeColeccion:
    id: str
    title: str
    start_year: int | None
    wishlist_policy: str
    wishlist_policy_label: str = ""
    politica_efectiva: str = ""
    politica_efectiva_label: str = ""


@dataclass(frozen=True)
class DetalleColeccion:
    id: str
    name: str
    description: str | None
    auto_search: str
    series: list[SerieDeColeccion]
    cover_series_id: str | None = None
    cover_series_title: str | None = None
    cover_series_valida: bool = False
    tiene_portada: bool = False
    portada_url: str = ""


@dataclass
class ResultadoColeccion:
    ok: bool
    errores: dict[str, str] = field(default_factory=dict)
    coleccion: Collection | None = None


def _validar_nombre(valor: str) -> tuple[str, str | None]:
    nombre = (valor or "").strip()
    if not nombre:
        return "", "El nombre no puede estar vacío."
    if len(nombre) > MAX_NOMBRE:
        return "", f"El nombre no puede superar {MAX_NOMBRE} caracteres."
    return nombre, None


def _validar_descripcion(valor: str) -> tuple[str | None, str | None]:
    descripcion = (valor or "").strip()
    if len(descripcion) > MAX_DESCRIPCION:
        return None, f"La descripción no puede superar {MAX_DESCRIPCION} caracteres."
    return descripcion or None, None


async def _nombre_ocupado(db: AsyncSession, nombre: str, *, salvo: UUID | None = None) -> bool:
    stmt = select(Collection.id).where(func.lower(Collection.name) == nombre.casefold())
    if salvo is not None:
        stmt = stmt.where(Collection.id != salvo)
    return (await db.execute(stmt)).first() is not None


def _politica(valor: str) -> CollectionAutoSearch | None:
    try:
        return CollectionAutoSearch((valor or "").strip().lower())
    except ValueError:
        return None


def _portada_url_de(coleccion: Collection, filas: list[Series], covers: Path) -> tuple[bool, str]:
    rutas = {str(s.id): portada_cacheada(covers, s.id) for s in filas}
    sobre_cache = (coleccion.cover_series_id is not None
                   and rutas.get(str(coleccion.cover_series_id)) is not None)
    hay = any(ruta is not None for ruta in rutas.values())
    partes = []
    for s in filas:
        ruta = rutas[str(s.id)]
        try:
            st = ruta.stat() if ruta is not None else None
            partes.append(f"{s.id}:{st.st_mtime_ns if st else 0}:{st.st_size if st else 0}")
        except OSError:
            partes.append(f"{s.id}:0:0")
    huella = hashlib.sha256("|".join(partes).encode()).hexdigest()[:12]
    base = str(coleccion.cover_series_id) if sobre_cache else "auto"
    return (sobre_cache or hay,
            f"/ui/colecciones/{coleccion.id}/portada?v={base}-{huella}-m{PORTADA_VERSION}")


async def listar_colecciones(db: AsyncSession) -> list[ColeccionResumen]:
    filas = (await db.execute(
        select(Collection, func.count(Series.id))
        .outerjoin(Series, Series.collection_id == Collection.id)
        .group_by(Collection.id)
        .order_by(func.lower(Collection.name), Collection.id)
    )).all()
    covers = Path(get_settings().covers_cache_path)
    por_coleccion: dict[str, list[Series]] = {}
    if filas:
        series = (await db.execute(select(Series).where(
            Series.collection_id.is_not(None)))).scalars().all()
        for s in series:
            por_coleccion.setdefault(str(s.collection_id), []).append(s)
    resumen = []
    for c, n in filas:
        tiene, url = _portada_url_de(c, por_coleccion.get(str(c.id), []), covers)
        resumen.append(ColeccionResumen(
            str(c.id), c.name, c.description, c.auto_search.value, int(n or 0),
            tiene_portada=tiene, portada_url=url))
    return resumen


async def detalle_coleccion(db: AsyncSession, coleccion_id: UUID) -> DetalleColeccion | None:
    coleccion = await db.get(Collection, coleccion_id)
    if coleccion is None:
        return None
    filas = (await db.execute(
        select(Series).where(Series.collection_id == coleccion_id)
        .order_by(Series.sort_title, Series.title)
    )).scalars().all()
    sobre = next((s for s in filas if s.id == coleccion.cover_series_id), None)
    covers = Path(get_settings().covers_cache_path)
    tiene, portada_url = _portada_url_de(coleccion, filas, covers)
    sobre_cache = tiene and sobre is not None and portada_cacheada(covers, sobre.id) is not None
    return DetalleColeccion(
        str(coleccion.id), coleccion.name, coleccion.description, coleccion.auto_search.value,
        [SerieDeColeccion(
            str(s.id), s.title, s.start_year,
            (s.wishlist_policy or WishlistPolicy.NONE.value),
            etiqueta_politica(s.wishlist_policy),
            politica_efectiva_de(s.wishlist_policy, coleccion.auto_search),
            etiqueta_politica(politica_efectiva_de(s.wishlist_policy, coleccion.auto_search)))
         for s in filas],
        cover_series_id=str(coleccion.cover_series_id) if coleccion.cover_series_id else None,
        cover_series_title=sobre.title if sobre else None,
        cover_series_valida=sobre_cache, tiene_portada=tiene,
        portada_url=portada_url)


async def crear_coleccion(db: AsyncSession, *, name: str, description: str,
                          auto_search: str = "heredar") -> ResultadoColeccion:
    nombre, error = _validar_nombre(name)
    descripcion, error_desc = _validar_descripcion(description)
    politica = _politica(auto_search)
    errores: dict[str, str] = {}
    if error:
        errores["name"] = error
    if error_desc:
        errores["description"] = error_desc
    if politica is None:
        errores["auto_search"] = "Elige una política válida."
    if not errores and await _nombre_ocupado(db, nombre):
        errores["name"] = "Ya existe una colección con ese nombre."
    if errores:
        return ResultadoColeccion(False, errores)
    coleccion = Collection(name=nombre, description=descripcion, auto_search=politica)
    db.add(coleccion)
    await db.flush()
    return ResultadoColeccion(True, coleccion=coleccion)


async def editar_coleccion(db: AsyncSession, coleccion_id: UUID, *, name: str,
                           description: str, auto_search: str) -> ResultadoColeccion:
    coleccion = await db.get(Collection, coleccion_id)
    if coleccion is None:
        return ResultadoColeccion(False, {"general": "La colección ya no existe."})
    nombre, error = _validar_nombre(name)
    descripcion, error_desc = _validar_descripcion(description)
    politica = _politica(auto_search)
    errores: dict[str, str] = {}
    if error:
        errores["name"] = error
    if error_desc:
        errores["description"] = error_desc
    if politica is None:
        errores["auto_search"] = "Elige una política válida."
    if not errores and await _nombre_ocupado(db, nombre, salvo=coleccion_id):
        errores["name"] = "Ya existe una colección con ese nombre."
    if errores:
        return ResultadoColeccion(False, errores, coleccion)
    coleccion.name = nombre
    coleccion.description = descripcion
    coleccion.auto_search = politica
    await db.flush()
    return ResultadoColeccion(True, coleccion=coleccion)


async def borrar_coleccion(db: AsyncSession, coleccion_id: UUID) -> bool:
    coleccion = await db.get(Collection, coleccion_id)
    if coleccion is None:
        return False
    await db.delete(coleccion)
    await db.flush()
    from zascarr.services.portada_coleccion import borrar_cache
    await borrar_cache(coleccion_id)      # best-effort; nunca impide borrar
    return True


async def series_sin_coleccion(db: AsyncSession, *, q: str = "",
                               tradicion: str = "") -> list[SerieDeColeccion]:
    """Series sin colección, con filtros tolerantes a acentos y artículos.

    `q` se normaliza con el MISMO normalizador que el matcher (`title_norm`);
    `tradicion` solo filtra si es un valor conocido. Orden estable y tope 200.
    """
    stmt = select(Series).where(Series.collection_id.is_(None))
    texto = (q or "").strip()[:120]
    if texto:
        normalizado = normalize_title(texto)
        if normalizado:
            stmt = stmt.where(Series.title_norm.like(f"%{normalizado}%"))
    if tradicion in {t.value for t in ComicTradition}:
        stmt = stmt.where(Series.tradition == ComicTradition(tradicion))
    filas = (await db.execute(
        stmt.order_by(Series.sort_title, Series.title).limit(200))).scalars().all()
    return [SerieDeColeccion(
        str(s.id), s.title, s.start_year,
        (s.wishlist_policy or WishlistPolicy.NONE.value),
        etiqueta_politica(s.wishlist_policy),
        politica_efectiva_de(s.wishlist_policy, None),
        etiqueta_politica(politica_efectiva_de(s.wishlist_policy, None)))
        for s in filas]


async def asignar_series(db: AsyncSession, coleccion_id: UUID,
                         serie_ids: list[UUID]) -> ResultadoColeccion:
    """Asigna VARIAS series de forma atómica: o todas o ninguna.

    Valida pertenencia y disponibilidad de todas antes de escribir; duplicados
    del formulario se colapsan. `asignar_serie` sigue siendo el envoltorio de una.
    """
    coleccion = await db.get(Collection, coleccion_id)
    if coleccion is None:
        return ResultadoColeccion(False, {"general": "La colección ya no existe."})
    unicos: list[UUID] = []
    vistos: set[UUID] = set()
    for sid in serie_ids:
        if sid not in vistos:
            vistos.add(sid)
            unicos.append(sid)
    if not unicos:
        return ResultadoColeccion(False, {"serie": "Elige al menos una serie."})
    filas = (await db.execute(
        select(Series).where(Series.id.in_(unicos)))).scalars().all()
    por_id = {s.id: s for s in filas}
    faltan = [str(sid) for sid in unicos if sid not in por_id]
    if faltan:
        return ResultadoColeccion(False, {
            "serie": "Alguna de las series elegidas ya no existe. No se ha añadido ninguna."})
    ocupadas = [s.title for s in filas if s.collection_id is not None]
    if ocupadas:
        return ResultadoColeccion(False, {
            "serie": "Estas series ya pertenecen a otra colección: "
                     + ", ".join(ocupadas) + ". No se ha añadido ninguna."})
    for serie in filas:
        serie.collection_id = coleccion_id
    await db.flush()
    return ResultadoColeccion(True, coleccion=coleccion)


async def asignar_serie(db: AsyncSession, coleccion_id: UUID, serie_id: UUID) -> ResultadoColeccion:
    return await asignar_series(db, coleccion_id, [serie_id])


async def quitar_serie(db: AsyncSession, coleccion_id: UUID, serie_id: UUID) -> bool:
    serie = await db.get(Series, serie_id)
    if serie is None or str(serie.collection_id) != str(coleccion_id):
        return False
    serie.collection_id = None
    await db.flush()
    return True
