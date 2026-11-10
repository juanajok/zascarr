# ruff: noqa: E501
"""#341/BL-WK3: CSV de la colección y de los deseados.

Dos exportaciones **de solo lectura**, en streaming: se recorre la consulta con `session.stream`
y se escribe/entrega fila a fila, sin construir una lista con toda la colección en memoria. UTF-8
con BOM (Excel/LibreOffice), encabezados en español y sin rutas del disco por defecto. No se envía
nada fuera de la instancia.
"""
from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Iterable
from datetime import date, datetime

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    Publisher,
    Series,
    Wishlist,
    WishlistPolicy,
    WishlistStatus,
)

BOM = "\ufeff"

CABECERAS_COLECCION = (
    "Serie", "Año", "Editorial", "Tradición", "Número", "Título", "Formato", "Estado",
)
CABECERAS_DESEADOS = (
    "Serie", "Número", "Estado", "Política de búsqueda", "Notas",
)

TRADICION_ES = {
    ComicTradition.AMERICAN: "americana",
    ComicTradition.FRANCO_BELGIAN: "franco-belga",
    ComicTradition.MANGA: "manga",
    ComicTradition.TEBEO: "tebeo",
    ComicTradition.FUMETTI: "fumetti",
    ComicTradition.MANHWA: "manhwa",
    ComicTradition.MANHUA: "manhua",
    ComicTradition.BRITISH: "británica",
    ComicTradition.OTHER: "otra",
}
ESTADO_DESEADO_ES = {
    WishlistStatus.WANTED: "deseado",
    WishlistStatus.SEARCHING: "buscando",
    WishlistStatus.DOWNLOADING: "descargando",
    WishlistStatus.DOWNLOADED: "descargado",
    WishlistStatus.IMPORTED: "importado",
    WishlistStatus.FAILED: "falló",
    WishlistStatus.RETIRADO: "retirado",
}
POLITICA_ES = {
    WishlistPolicy.NONE: "no busca sola",
    WishlistPolicy.MISSING: "faltantes",
    WishlistPolicy.FUTURE: "futuros",
    WishlistPolicy.ALL: "todos",
}


def _texto(valor: object | None) -> str:
    return "" if valor is None else str(valor)


def _anio(issue_date: date | datetime | None, start_year: int | None) -> str:
    if isinstance(issue_date, (date, datetime)):
        return str(issue_date.year)
    return _texto(start_year)


def _formato(formato: FileFormat | str | None) -> str:
    if formato is None:
        return ""
    return getattr(formato, "value", str(formato)).upper()


async def filas_coleccion(db: AsyncSession) -> AsyncIterator[tuple[str, ...]]:
    """Una fila por archivo registrado (un número puede tener varios)."""
    stmt = (
        select(
            Series.title, Series.start_year, Series.tradition, Publisher.name,
            Issue.issue_number, Issue.title, Issue.release_date,
            File.file_format, File.is_missing,
        )
        .select_from(File)
        .join(Issue, File.issue_id == Issue.id)
        .join(Series, Issue.series_id == Series.id)
        .outerjoin(Publisher, Series.publisher_id == Publisher.id)
        .order_by(Series.sort_title, Series.title, Issue.sort_order, Issue.issue_number, File.id)
    )
    result = await db.stream(stmt)
    async for fila in result:
        (titulo, start_year, tradicion, editorial, numero, titulo_issue,
         fecha, formato, falta) = fila
        anio = _anio(fecha, start_year)
        trad = TRADICION_ES.get(tradicion, _texto(getattr(tradicion, "value", tradicion)))
        estado = "falta" if bool(falta) else "tengo"
        yield (
            _texto(titulo), anio, _texto(editorial), trad, _texto(numero),
            _texto(titulo_issue), _formato(formato), estado,
        )


async def filas_deseados(db: AsyncSession) -> AsyncIterator[tuple[str, ...]]:
    stmt = (
        select(
            Series.title, Issue.issue_number, Wishlist.numero, Wishlist.status,
            Series.wishlist_policy, Wishlist.notes,
        )
        .select_from(Wishlist)
        .outerjoin(Issue, Wishlist.issue_id == Issue.id)
        .outerjoin(Series, or_(Wishlist.series_id == Series.id,
                               Issue.series_id == Series.id))
        .order_by(Series.sort_title, Series.title, Issue.sort_order, Wishlist.numero, Wishlist.id)
    )
    result = await db.stream(stmt)
    async for fila in result:
        titulo, numero_issue, numero_deseo, estado, politica, notas = fila
        numero = _texto(numero_issue) if numero_issue is not None else _texto(numero_deseo)
        estado_txt = ESTADO_DESEADO_ES.get(estado, _texto(getattr(estado, "value", estado)))
        politica_txt = POLITICA_ES.get(politica, _texto(getattr(politica, "value", politica)))
        yield (_texto(titulo), numero, estado_txt, politica_txt, _texto(notas))


async def generar_csv(
    filas: AsyncIterator[tuple[str, ...]], cabecera: Iterable[str],
) -> AsyncIterator[bytes]:
    """Cabecera + filas, con BOM y `\\r\\n`; no acumula filas."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    buffer.write(BOM)
    writer.writerow(tuple(cabecera))
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)
    async for fila in filas:
        writer.writerow(tuple(fila))
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
