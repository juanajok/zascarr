"""#1027/ADR 0022: alta manual de una obra autoconclusiva.

Una obra one-shot es una `Series.kind=ONE_SHOT` con **una** publicación. El
número solo se copia si la fuente lo da; la UI normal no lo pide y el `Issue`
queda con `issue_number=NULL` (ADR 0016). El archivo se enlaza sin moverlo, por
el mismo camino seguro que el alta de especiales (`File.issue_id` + metadatos).
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import (
    ComicTradition,
    File,
    Issue,
    IssueFormat,
    Series,
    SeriesKind,
)

#: Formatos de presentación razonables para una obra única (nunca `single_issue`).
FORMATOS_OBRA = (
    IssueFormat.GRAPHIC_NOVEL,
    IssueFormat.TRADE_PAPERBACK,
    IssueFormat.HARDCOVER,
    IssueFormat.ALBUM,
    IssueFormat.MANGA_TANKOBON,
    IssueFormat.DIGITAL,
)


class ObraAutoconclusivaError(ValueError):
    """Datos insuficientes o incoherentes para crear la obra."""


async def crear_obra_autoconclusiva(
    db: AsyncSession, file_id, titulo: str,
    formato: IssueFormat | str = IssueFormat.GRAPHIC_NOVEL,
    *,
    tradicion: ComicTradition | str = ComicTradition.AMERICAN,
    numero: str | None = None,
) -> tuple[Series, Issue]:
    """Crea la serie + su publicación y enlaza el archivo sin moverlo.

    No inventa `#1`: `numero` solo se copia si quien llama lo trae de una fuente.
    El llamador hace el commit; aquí solo se hace `flush`.
    """
    titulo = (titulo or "").strip()
    if not titulo:
        raise ObraAutoconclusivaError("El título de la obra no puede estar vacío")
    if len(titulo) > 500:
        raise ObraAutoconclusivaError("El título de la obra es demasiado largo")
    try:
        formato_issue = IssueFormat(formato)
    except ValueError as exc:
        raise ObraAutoconclusivaError("Formato de publicación no válido") from exc
    if formato_issue not in FORMATOS_OBRA:
        raise ObraAutoconclusivaError(
            "Una obra autoconclusiva no puede ser una grapa; elige novela gráfica, "
            "tomo, tapa dura, álbum o tomo de manga")
    try:
        trad = ComicTradition(tradicion)
    except ValueError as exc:
        raise ObraAutoconclusivaError("Tradición no válida") from exc
    archivo = await db.get(File, file_id)
    if archivo is None:
        raise ObraAutoconclusivaError("Archivo no encontrado")
    if archivo.issue_id is not None:
        raise ObraAutoconclusivaError("El archivo ya está enlazado a una publicación")
    numero_limpio = (numero or "").strip() or None
    if numero_limpio is not None and not numero_limpio.isdigit():
        raise ObraAutoconclusivaError("El número de la fuente no es válido")

    serie = Series(
        title=titulo, tradition=trad, kind=SeriesKind.ONE_SHOT,
        status="completed", metadata_source="manual",
    )
    db.add(serie)
    await db.flush()
    issue = Issue(
        series_id=serie.id, issue_number=numero_limpio, title=titulo,
        format=formato_issue, locked_fields=["series_id"],
        metadata_={"origen": "manual_one_shot"},
        metadata_source="manual",
    )
    db.add(issue)
    await db.flush()
    archivo.issue_id = issue.id
    archivo.metadata_ = {
        **(archivo.metadata_ or {}),
        "match_status": "manual_one_shot",
    }
    await db.flush()
    return serie, issue


def es_publicacion_unica(series: Series, publicaciones: int) -> bool:
    """¿Se puede marcar como one-shot? Una obra autoconclusiva tiene ≤1 publicación."""
    return publicaciones <= 1 or series.kind == SeriesKind.ONE_SHOT
