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

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from zascarr.models import (
    ComicTradition,
    File,
    FileFormat,
    Issue,
    Note,
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
CABECERAS_COLECCION_CON_NOTAS = CABECERAS_COLECCION + ("Nota de la serie", "Nota del número")
CABECERAS_DESEADOS = (
    "Serie", "Número", "Estado", "Política de búsqueda", "Notas",
)

#: Fórmulas de hoja de cálculo: una celda que empiece por uno de estos caracteres
#: (aunque lleve espacios delante) se ejecuta al abrir el CSV. Se neutraliza con
#: un apóstrofo inicial, que Excel/LibreOffice tratan como texto literal.
_INICIO_PELIGROSO = ("=", "+", "-", "@")


def _celda_segura(valor: object | None) -> str:
    texto = "" if valor is None else str(valor)
    if texto.lstrip().startswith(_INICIO_PELIGROSO):
        return "'" + texto
    return texto

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


async def filas_coleccion(
    db: AsyncSession, *, incluir_notas: bool = False,
) -> AsyncIterator[tuple[str, ...]]:
    """Una fila por archivo registrado (un número puede tener varios).

    Con `incluir_notas`, añade la nota de la serie y la del número al final; sin
    el flag no se emiten esas columnas. Las notas van por alias para no duplicar
    filas (una nota por serie y otra por número).
    """
    nota_serie = aliased(Note)
    nota_numero = aliased(Note)
    stmt = (
        select(
            Series.title, Series.start_year, Series.tradition, Publisher.name,
            Issue.issue_number, Issue.title, Issue.release_date,
            File.file_format, File.is_missing,
            nota_serie.texto, nota_numero.texto,
        )
        .select_from(File)
        .join(Issue, File.issue_id == Issue.id)
        .join(Series, Issue.series_id == Series.id)
        .outerjoin(Publisher, Series.publisher_id == Publisher.id)
        .outerjoin(nota_serie, and_(
            nota_serie.series_id == Series.id, nota_serie.issue_id.is_(None)))
        .outerjoin(nota_numero, nota_numero.issue_id == Issue.id)
        .order_by(Series.sort_title, Series.title, Issue.sort_order, Issue.issue_number, File.id)
    )
    result = await db.stream(stmt)
    async for fila in result:
        (titulo, start_year, tradicion, editorial, numero, titulo_issue,
         fecha, formato, falta, texto_serie, texto_numero) = fila
        anio = _anio(fecha, start_year)
        trad = TRADICION_ES.get(tradicion, _texto(getattr(tradicion, "value", tradicion)))
        estado = "falta" if bool(falta) else "tengo"
        valores = (
            _texto(titulo), anio, _texto(editorial), trad, _texto(numero),
            _texto(titulo_issue), _formato(formato), estado,
        )
        if incluir_notas:
            valores += (_texto(texto_serie), _texto(texto_numero))
        yield valores


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
        # Solo las celdas de datos: la cabecera no se toca y el BOM/CRLF se mantienen.
        writer.writerow(tuple(_celda_segura(valor) for valor in fila))
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)
