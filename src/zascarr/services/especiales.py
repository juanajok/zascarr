"""Alta manual de una publicación sin número editorial.

Un especial o tomo puede ser una publicación identificable por título y
formato aunque no tenga un número en el nombre. Se representa con un `Issue`
normal de `issue_number=NULL`; el archivo se enlaza sin moverlo.

No crea Issues el matcher: este camino es SOLO manual. Ver ADR 0016.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, Issue, IssueFormat, Series

#: Formatos que puede declarar una persona para un especial/tomo sin número.
FORMATOS_ESPECIAL = (
    IssueFormat.GRAPHIC_NOVEL,
    IssueFormat.TRADE_PAPERBACK,
    IssueFormat.HARDCOVER,
    IssueFormat.OMNIBUS,
)


class EspecialSinNumeroError(ValueError):
    """El archivo, la serie, el título o el formato no permiten el alta."""


class EspecialesService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def vincular_especial(
        self,
        file_id,
        series_id,
        titulo: str,
        formato: IssueFormat | str = IssueFormat.GRAPHIC_NOVEL,
        *,
        mover: bool = False,
    ) -> Issue:
        """Crea (o reutiliza) un Issue sin número y enlaza el archivo.

        Con `mover=True` lo mueve a `…/{Serie (Año)}/Especiales/{archivo}` (carpeta
        de la serie, creada si no existe). Sin `mover`, no toca el archivo. El
        llamador es responsable del commit; este servicio solo hace flush.
        """
        titulo = (titulo or "").strip()
        if not titulo:
            raise EspecialSinNumeroError("El título del especial no puede estar vacío")
        if len(titulo) > 500:
            raise EspecialSinNumeroError("El título del especial es demasiado largo")

        try:
            formato_issue = IssueFormat(formato)
        except ValueError as exc:
            raise EspecialSinNumeroError(f"Formato de especial no válido: {formato}") from exc
        if formato_issue not in FORMATOS_ESPECIAL:
            raise EspecialSinNumeroError(
                "Un especial sin número no puede ser single_issue; "
                "indica graphic_novel, trade_paperback, hardcover u omnibus"
            )

        archivo = await self.db.get(File, file_id)
        if archivo is None:
            raise EspecialSinNumeroError("Archivo no encontrado")
        if archivo.issue_id is not None:
            raise EspecialSinNumeroError("El archivo ya está enlazado a un Issue")

        serie = await self.db.get(Series, series_id)
        if serie is None:
            raise EspecialSinNumeroError("Serie no encontrada")

        issue = Issue(
            series_id=serie.id,
            issue_number=None,
            title=titulo,
            format=formato_issue,
            locked_fields=["series_id"],
            metadata_={"sin_numero": True, "origen": "manual"},
            metadata_source="manual",
        )
        self.db.add(issue)
        await self.db.flush()

        archivo.issue_id = issue.id
        archivo.metadata_ = {
            **(archivo.metadata_ or {}),
            "sin_numero": True,
            "match_status": "manual_especial",
        }

        if mover:
            from zascarr.services.importer import build_library_path
            from zascarr.services.raices import raiz_por_tradicion
            from zascarr.utils.fs import safe_move_async

            raiz = await raiz_por_tradicion(self.db, serie.tradition)
            if raiz is None:
                raise EspecialSinNumeroError(
                    "No hay una raíz de biblioteca activa para esa tradición")
            origen = Path(archivo.file_path)
            destino = build_library_path(
                Path(raiz.path), serie, None, origen.suffix,
                fallback_name=origen.name, especial=True)
            final = await safe_move_async(origen, destino)
            archivo.file_path = str(final)
            archivo.file_name = final.name

        await self.db.flush()
        return issue
