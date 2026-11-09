"""ETQ2 (#538): aplicar a una serie las etiquetas y géneros de su ComicInfo.

Este módulo **no parsea XML ni escribe el CBZ**: recibe las listas ya separadas
y acotadas por `core/importer_triage.py` y las aplica a la serie:

- Etiquetas con `source='comicinfo_xml'`, `weight=NULL` y `oculta=false`.
- Géneros **solo si la serie no tenía ninguno** (no se pisa lo que ya haya).

Reglas que hereda de ETQ1a: una fila `manual` no se modifica ni se sustituye,
y una fila de fuente marcada `oculta=true` no se resucita en el siguiente ciclo
(FR-05). Todo es idempotente: repetir la importación no duplica filas.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import Genre, Tag, series_genres, series_tags
from zascarr.services.etiquetas import (
    NAMESPACE,
    SOURCE_COMICINFO_XML,
    EtiquetaInvalida,
    validar_nombre,
)

#: `genres.name` es VARCHAR(100); el parser ya recorta a 64, pero el servicio
#: se defiende de llamadas directas.
MAX_NOMBRE_GENERO = 100


@dataclass(frozen=True)
class ResultadoComicInfo:
    """Lo que cambió al aplicar un ComicInfo a la serie, para el informe."""

    etiquetas: int = 0
    etiquetas_ignoradas: int = 0
    generos: int = 0
    avisos: tuple[str, ...] = ()


async def _tags_por_norm(db: AsyncSession, normalizados: tuple[str, ...]) -> dict[str, Tag]:
    if not normalizados:
        return {}
    filas = await db.execute(
        select(Tag).where(Tag.namespace == NAMESPACE, Tag.name_norm.in_(normalizados))
    )
    return {tag.name_norm: tag for tag in filas.scalars().all()}


async def _generos_por_nombre(db: AsyncSession, nombres: tuple[str, ...]) -> dict[str, Genre]:
    """Géneros existentes por nombre en minúsculas (para no duplicar «Horror»/«horror»)."""
    if not nombres:
        return {}
    filas = await db.execute(
        select(Genre).where(func.lower(Genre.name).in_(tuple(n.lower() for n in nombres)))
    )
    return {genero.name.lower(): genero for genero in filas.scalars().all()}


async def _aplicar_etiquetas(db: AsyncSession, series_id: UUID, nombres: list[str], *,
                             avisos: list[str]) -> tuple[int, int]:
    validos: dict[str, str] = {}
    ignoradas = 0
    for bruto in nombres:
        try:
            nombre, normalizado = validar_nombre(bruto)
        except EtiquetaInvalida:
            ignoradas += 1
            continue
        validos.setdefault(normalizado, nombre)

    if ignoradas:
        avisos.append(f"{ignoradas} etiquetas de ComicInfo no son válidas; se ignoran")

    if not validos:
        return 0, ignoradas

    existentes = await _tags_por_norm(db, tuple(validos))
    faltan = [
        {"name": nombre, "namespace": NAMESPACE}
        for normalizado, nombre in validos.items() if normalizado not in existentes
    ]
    if faltan:
        # `ON CONFLICT` en vez de capturar IntegrityError: un rollback a mitad
        # del ciclo de importación tiraría el resto del trabajo de la sesión.
        await db.execute(
            pg_insert(Tag).values(faltan).on_conflict_do_nothing(
                constraint="uq_tags_namespace_name_norm"
            )
        )
        existentes = await _tags_por_norm(db, tuple(validos))

    ids = tuple(tag.id for tag in existentes.values())
    filas = (await db.execute(
        select(series_tags.c.tag_id, series_tags.c.source, series_tags.c.oculta)
        .where(series_tags.c.series_id == series_id, series_tags.c.tag_id.in_(ids))
    )).all()
    por_tag = {fila.tag_id: fila for fila in filas}

    nuevas: list[dict] = []
    for tag in existentes.values():
        fila = por_tag.get(tag.id)
        if fila is None:
            nuevas.append({
                "series_id": series_id, "tag_id": tag.id,
                "source": SOURCE_COMICINFO_XML, "weight": None, "oculta": False,
            })
        # Si ya existe (manual, de otra fuente u oculta) NO se toca: `manual`
        # gana y una etiqueta quitada desde la ficha no resucita.
    if nuevas:
        await db.execute(
            pg_insert(series_tags).values(nuevas).on_conflict_do_nothing(
                index_elements=["series_id", "tag_id"]
            )
        )
    return len(nuevas), ignoradas


async def _aplicar_generos(db: AsyncSession, series_id: UUID, nombres: list[str], *,
                           avisos: list[str]) -> int:
    if not nombres:
        return 0
    ya_tiene = await db.scalar(
        select(func.count()).select_from(series_genres)
        .where(series_genres.c.series_id == series_id)
    )
    if ya_tiene:
        avisos.append("La serie ya tenía géneros; no se añaden los de ComicInfo")
        return 0

    validos: dict[str, str] = {}
    for bruto in nombres:
        nombre = (bruto or "").strip()
        if not nombre:
            continue
        if len(nombre) > MAX_NOMBRE_GENERO:
            avisos.append("Un género de ComicInfo supera 100 caracteres; se ignora")
            continue
        validos.setdefault(nombre.lower(), nombre)

    if not validos:
        return 0

    existentes = await _generos_por_nombre(db, tuple(validos.values()))
    faltan = [
        {"name": nombre}
        for clave, nombre in validos.items() if clave not in existentes
    ]
    if faltan:
        await db.execute(
            pg_insert(Genre).values(faltan).on_conflict_do_nothing(
                index_elements=["name"]
            )
        )
        existentes = await _generos_por_nombre(db, tuple(validos.values()))

    enlaces = [
        {"series_id": series_id, "genre_id": genero.id}
        for genero in existentes.values()
    ]
    if enlaces:
        await db.execute(
            pg_insert(series_genres).values(enlaces).on_conflict_do_nothing(
                index_elements=["series_id", "genre_id"]
            )
        )
    return len(enlaces)


async def aplicar_comicinfo(
    db: AsyncSession, series_id: UUID, *, tags: list[str], genres: list[str]
) -> ResultadoComicInfo:
    """Aplica `<Tags>`/`<Genre>` a la serie. Idempotente y sin tocar `manual`.

    No hace `commit`: el importador decide cuándo cerrar la transacción.
    """
    avisos: list[str] = []
    etiquetas, ignoradas = await _aplicar_etiquetas(
        db, series_id, tags, avisos=avisos)
    generos = await _aplicar_generos(db, series_id, genres, avisos=avisos)
    return ResultadoComicInfo(
        etiquetas=etiquetas,
        etiquetas_ignoradas=ignoradas,
        generos=generos,
        avisos=tuple(avisos),
    )
