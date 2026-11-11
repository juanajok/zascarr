"""BL-R7 (#236): vistas de trabajo predefinidas, como CONSULTAS (sin tablas).

Cada vista es una condición viva: un archivo entra o sale según su estado, no se
guarda pertenencia. Las listas se recortan en SQL (LIMIT/OFFSET); el recuento es
una consulta aparte, no se materializa el conjunto completo. Solo lectura.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, Series
from zascarr.services.disponibilidad import contar_no_disponibles

POR_PAGINA = 50

#: (clave, título, descripción, url). El orden es el de la pantalla.
VISTAS: tuple[tuple[str, str, str, str], ...] = (
    ("sin-identificar", "Sin identificar",
     "Archivos que todavía no saben a qué publicación pertenecen.",
     "/ui/vistas/sin-identificar"),
    ("dudosas", "Identificación dudosa",
     "Archivos cuya identificación no es segura y conviene revisar.",
     "/ui/vistas/dudosas"),
    ("discrepancias", "Con discrepancias",
     "Relaciones protegidas con una propuesta distinta pendiente.",
     "/ui/vistas/discrepancias"),
    ("no-disponibles", "No disponibles",
     "Archivos que ZascArr no encuentra en su ruta.",
     "/ui/no-disponibles"),
    ("variantes", "Con varias variantes",
     "Publicaciones con más de un contenido distinto.",
     "/ui/vistas/variantes"),
)
CLAVES = tuple(v[0] for v in VISTAS)
_NO_SERIE = "Sin serie asignada"


@dataclass(frozen=True)
class FilaVista:
    titulo: str
    detalle: str
    formato: str = ""
    tamano: int | None = None
    url: str | None = None


@dataclass(frozen=True)
class PaginaVista:
    clave: str
    titulo: str
    descripcion: str
    filas: list[FilaVista]
    total: int
    pagina: int
    paginas: int
    desde: int
    hasta: int


@dataclass(frozen=True)
class ResumenVista:
    clave: str
    titulo: str
    descripcion: str
    url: str
    recuento: int


def _condicion_sin_identificar():
    # Pendiente sin publicación: no se apoya en la ruta (bug B11) ni en un estado de match.
    return (File.issue_id.is_(None), File.review_dismissed.is_(False))


def _condicion_dudosa():
    return (File.metadata_["match_status"].astext == "fuzzy",
            File.review_dismissed.is_(False))


def _condicion_discrepancias():
    return File.metadata_.contains({"discrepancias": [{"estado": "pendiente"}]})


def _subconsulta_variantes():
    """Publicaciones con ≥2 archivos y ≥2 contenidos distintos (hash u original)."""
    huella = func.coalesce(File.sha256_hash, File.original_sha256)
    return (
        select(
            Issue.id.label("issue_id"), Issue.issue_number, Series.id.label("series_id"),
            Series.title, func.count(File.id).label("archivos"),
            func.count(func.distinct(huella)).label("contenidos"),
            func.count(File.id).filter(File.is_missing.is_(False)).label("disponibles"),
        )
        .join(Issue, File.issue_id == Issue.id)
        .join(Series, Issue.series_id == Series.id)
        .group_by(Issue.id, Issue.issue_number, Series.id, Series.title)
        .having(func.count(File.id) >= 2, func.count(func.distinct(huella)) >= 2)
        .subquery()
    )


def _paginacion(total: int, pagina: int) -> tuple[int, int, int, int]:
    paginas = max(1, (total + POR_PAGINA - 1) // POR_PAGINA)
    pagina = min(max(1, pagina), paginas)
    desde = (pagina - 1) * POR_PAGINA
    hasta = min(desde + POR_PAGINA, total)
    return pagina, paginas, desde, hasta


def _url_de_ficha(series_id, issue_id) -> str | None:
    if series_id is None or issue_id is None:
        return None
    return f"/ui/series/{series_id}/numero/{issue_id}"


async def _contar(consulta, db: AsyncSession) -> int:
    return (await db.execute(consulta)).scalar_one()


async def contar_vistas(db: AsyncSession) -> dict[str, int]:
    """Recuento de las cinco vistas. Consultas de conteo, sin materializar filas."""
    sin_identificar = await _contar(
        select(func.count()).select_from(File).where(*_condicion_sin_identificar()), db)
    dudosas = await _contar(
        select(func.count()).select_from(File).where(*_condicion_dudosa()), db)
    discrepancias = await _contar(
        select(func.count()).select_from(File).where(_condicion_discrepancias()), db)
    no_disponibles = await contar_no_disponibles(db)
    variantes = await _contar(
        select(func.count()).select_from(_subconsulta_variantes()), db)
    return {"sin-identificar": sin_identificar, "dudosas": dudosas,
            "discrepancias": discrepancias, "no-disponibles": no_disponibles,
            "variantes": variantes}


async def resumen_de_vistas(db: AsyncSession) -> list[ResumenVista]:
    cuentas = await contar_vistas(db)
    return [ResumenVista(clave, titulo, descripcion, url, cuentas.get(clave, 0))
            for clave, titulo, descripcion, url in VISTAS]


def _pagina(clave: str, titulo: str, descripcion: str, filas: list[FilaVista],
            total: int, pagina: int) -> PaginaVista:
    pagina, paginas, desde, hasta = _paginacion(total, pagina)
    return PaginaVista(clave, titulo, descripcion, filas, total, pagina, paginas, desde, hasta)


async def _listar_sin_identificar(db: AsyncSession, pagina: int) -> PaginaVista:
    condicion = _condicion_sin_identificar()
    total = await _contar(select(func.count()).select_from(File).where(*condicion), db)
    pagina, _p, desde, _h = _paginacion(total, pagina)
    filas = (await db.execute(
        select(File.file_name, File.file_format, File.file_size_bytes)
        .where(*condicion)
        .order_by(File.imported_at.desc(), File.id)
        .offset(desde).limit(POR_PAGINA))).all()
    return _pagina(
        "sin-identificar", "Sin identificar",
        "Archivos que aún no tienen una publicación asignada. Se revisan desde «Por revisar».",
        [FilaVista(f.file_name, _NO_SERIE, f.file_format.value.upper(), f.file_size_bytes,
                   "/ui/pendientes")
         for f in filas], total, pagina)


async def _listar_dudosas(db: AsyncSession, pagina: int) -> PaginaVista:
    condicion = _condicion_dudosa()
    total = await _contar(select(func.count()).select_from(File).where(*condicion), db)
    pagina, _p, desde, _h = _paginacion(total, pagina)
    filas = (await db.execute(
        select(File.file_name, File.file_format, File.file_size_bytes,
               Issue.id.label("issue_id"), Issue.issue_number,
               Series.id.label("series_id"), Series.title)
        .outerjoin(Issue, File.issue_id == Issue.id)
        .outerjoin(Series, Issue.series_id == Series.id)
        .where(*condicion)
        .order_by(File.imported_at.desc(), File.id)
        .offset(desde).limit(POR_PAGINA))).all()
    return _pagina(
        "dudosas", "Identificación dudosa",
        "Archivos con identificación fuzzy (no exacta): revísalos antes de confiar.",
        [FilaVista(
            f.file_name,
            f"{f.title} · nº {f.issue_number}" if f.title else _NO_SERIE,
            f.file_format.value.upper(), f.file_size_bytes,
            _url_de_ficha(f.series_id, f.issue_id))
         for f in filas], total, pagina)


async def _listar_discrepancias(db: AsyncSession, pagina: int) -> PaginaVista:
    condicion = _condicion_discrepancias()
    total = await _contar(select(func.count()).select_from(File).where(condicion), db)
    pagina, _p, desde, _h = _paginacion(total, pagina)
    filas = (await db.execute(
        select(File.file_name, File.file_format, File.file_size_bytes,
               Issue.id.label("issue_id"), Issue.issue_number,
               Series.id.label("series_id"), Series.title)
        .outerjoin(Issue, File.issue_id == Issue.id)
        .outerjoin(Series, Issue.series_id == Series.id)
        .where(condicion)
        .order_by(File.imported_at.desc(), File.id)
        .offset(desde).limit(POR_PAGINA))).all()
    return _pagina(
        "discrepancias", "Con discrepancias",
        "Relaciones protegidas con una propuesta distinta pendiente. No se aplica sola: se revisa.",
        [FilaVista(
            f.file_name,
            f"{f.title} · nº {f.issue_number}" if f.title else "Propuesta pendiente",
            f.file_format.value.upper(), f.file_size_bytes,
            _url_de_ficha(f.series_id, f.issue_id))
         for f in filas], total, pagina)


async def _listar_variantes(db: AsyncSession, pagina: int) -> PaginaVista:
    sub = _subconsulta_variantes()
    total = await _contar(select(func.count()).select_from(sub), db)
    pagina, _p, desde, _h = _paginacion(total, pagina)
    filas = (await db.execute(
        select(sub.c.series_id, sub.c.issue_id, sub.c.title, sub.c.issue_number,
               sub.c.archivos, sub.c.contenidos, sub.c.disponibles)
        .order_by(sub.c.title, sub.c.issue_number)
        .offset(desde).limit(POR_PAGINA))).all()
    return _pagina(
        "variantes", "Con varias variantes",
        "Publicaciones con más de un archivo y más de un contenido distinto. "
        "Las copias exactas no cuentan aquí.",
        [FilaVista(
            f"#{f.issue_number} · {f.title}",
            f"{f.archivos} archivos · {f.contenidos} contenidos distintos · "
            f"{f.disponibles} en el disco",
            "", None, _url_de_ficha(f.series_id, f.issue_id))
         for f in filas], total, pagina)


async def listar_vista(db: AsyncSession, clave: str, pagina: int = 1) -> PaginaVista | None:
    """Una página de la vista, recortada en SQL. `None` si la clave no existe."""
    if clave == "sin-identificar":
        return await _listar_sin_identificar(db, pagina)
    if clave == "dudosas":
        return await _listar_dudosas(db, pagina)
    if clave == "discrepancias":
        return await _listar_discrepancias(db, pagina)
    if clave == "variantes":
        return await _listar_variantes(db, pagina)
    return None


__all__ = [
    "CLAVES", "VISTAS", "FilaVista", "PaginaVista", "ResumenVista",
    "contar_vistas", "listar_vista", "resumen_de_vistas",
]
