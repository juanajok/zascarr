"""
ReviewService — acciones de la bandeja de pendientes (B2).

Archivos que el importer no supo clasificar viven en _Unsorted/ con
issue_id=None. El coleccionista los resuelve a mano desde la UI:
  - asignar a una serie existente, creando el Issue si el número no
    existe todavía (el caso más común: la mayoría de archivos en
    _Unsorted no tienen un Issue esperando ya en la BD).
  - ignorar: se deja de mostrar en la bandeja para siempre.

Una asignación manual confirmada por el coleccionista es EXACTAMENTE el
caso para el que existe la convención metadata_source='manual' (fix C3
del peer review): el File se marca así y el enricher nunca lo toca (los
archivos no son su terreno). El Issue nuevo, en cambio, NO se marca
'manual' — eso bloquearía sinopsis/portada/créditos que el enricher sí
debería poder rellenar más adelante — sino que protege únicamente la
asignación serie+número vía locked_fields (H3, peer review v2).
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, Issue, MetadataSource, Series
from zascarr.services.importer import build_library_path
from zascarr.utils.fs import safe_move_async


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._library = get_settings().library_path

    async def pending_files(self, limit: int = 50) -> list[File]:
        """Archivos en _Unsorted/ que nadie ha resuelto ni descartado."""
        unsorted_prefix = str(self._library / "_Unsorted")
        return list((await self.db.execute(
            select(File)
            .where(File.issue_id.is_(None))
            .where(File.review_dismissed.is_(False))
            .where(File.file_path.startswith(unsorted_prefix))
            .order_by(File.imported_at.desc())
            .limit(limit)
        )).scalars().all())

    async def search_series(self, query: str, limit: int = 20) -> list[Series]:
        """Búsqueda manual para el selector de la bandeja: coincidencia
        parcial de título, no la lógica estricta de SeriesMatcher (esa es
        para decidir sola; aquí decide una persona mirando la pantalla)."""
        query = (query or "").strip()
        if not query:
            return []
        return list((await self.db.execute(
            select(Series)
            .where(Series.title.ilike(f"%{query}%"))
            .order_by(Series.title)
            .limit(limit)
        )).scalars().all())

    async def assign_to_series(self, file_id, series_id, issue_number: str) -> File:
        issue_number = (issue_number or "").strip()
        if not issue_number:
            raise ValueError("El número de issue no puede estar vacío")

        file = await self.db.get(File, file_id)
        if not file:
            raise ValueError("Archivo no encontrado")

        series = await self.db.get(Series, series_id)
        if not series:
            raise ValueError("Serie no encontrada")

        issue = (await self.db.execute(
            select(Issue)
            .where(Issue.series_id == series.id)
            .where(Issue.issue_number == issue_number)
        )).scalar_one_or_none()
        if not issue:
            # H3 (peer review v2): antes se marcaba metadata_source='manual',
            # lo que bloqueaba TODO el issue para el enricher (sinopsis,
            # portada, créditos incluidos) solo por proteger la asignación
            # serie+número que hizo el coleccionista. locked_fields protege
            # justo eso y deja que el resto se siga rellenando.
            issue = Issue(
                series_id=series.id,
                issue_number=issue_number,
                locked_fields=["series_id", "issue_number"],
            )
            self.db.add(issue)
            await self.db.flush()

        orig = Path(file.file_path)
        dest = build_library_path(self._library, series, issue_number, orig.suffix)
        # A3: mover a destino verificado — nunca sobreescribe ni borra el
        # original hasta que la copia está completa (ver utils/fs.safe_move).
        final_dest = await safe_move_async(orig, dest)

        file.issue_id = issue.id
        file.file_path = str(final_dest)
        file.file_name = final_dest.name
        file.metadata_source = MetadataSource.MANUAL.value
        await self.db.flush()
        return file

    async def dismiss(self, file_id) -> None:
        file = await self.db.get(File, file_id)
        if not file:
            raise ValueError("Archivo no encontrado")
        file.review_dismissed = True
        await self.db.flush()
