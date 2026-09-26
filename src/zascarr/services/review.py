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

Cada asignación manual también alimenta el alias local de B13
(`_learn_alias`): el patrón de nombre que llevó a este archivo a
Pendientes queda memorizado → la serie elegida, para que
SeriesMatcher.decide() no vuelva a preguntar la próxima vez.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import File, Issue, IssueFormat, LocalAlias, MetadataSource, Series
from zascarr.services.importer import build_library_path
from zascarr.utils.fs import safe_move_async
from zascarr.utils.naming import parse_comic_filename

# B15 (2026-09-26): qué Issue.format corresponde a cada edition_kind que
# puede salir de naming.py — nunca SINGLE_ISSUE por defecto para estos,
# porque el número que llevan no es una grapa estándar (es el tomo de
# una recopilación o edición). "omnigold"/"integral" agrupan varias
# grapas originales (más cerca de un ómnibus); "tomo"/"volumen" a secas
# son la unidad de publicación de una obra por tomos (manga/BD).
_EDITION_KIND_A_FORMAT = {
    "omnigold": IssueFormat.OMNIBUS,
    "integral": IssueFormat.OMNIBUS,
    "tomo": IssueFormat.TRADE_PAPERBACK,
    "volumen": IssueFormat.TRADE_PAPERBACK,
}


class ReviewService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._library = get_settings().library_path

    async def pending_files(self, limit: int = 50) -> list[File]:
        """Archivos sin match fiable que nadie ha resuelto ni descartado.

        Bug real (reportado, B11): filtraba por vivir bajo `_Unsorted/`
        en disco — un proxy que solo es cierto para el importer de
        descargas (que SÍ mueve ahí lo que no reconoce). LibraryAdopter
        (B11) registra los archivos sin match EN SU SITIO REAL, nunca
        los mueve — con el filtro de ruta, quedaban invisibles en
        Pendientes para siempre, aunque `issue_id` fuera NULL.

        `issue_id IS NULL` por sí solo tampoco vale: una serie SÍ
        identificada pero sin el número exacto (issue_id NULL, hueco del
        enricher, D1) también lo cumple y esa NO es la bandeja de
        Pendientes — se resuelve sola cuando el enricher encuentre el
        número. La señal correcta es `match_status == 'unsorted'`
        (guardado en `metadata_` por Importer/LibraryAdopter, el mismo
        criterio con el que ambos deciden mover/registrar en _Unsorted o
        no), no la ruta ni solo el issue_id.
        """
        return list((await self.db.execute(
            select(File)
            .where(File.issue_id.is_(None))
            .where(File.review_dismissed.is_(False))
            .where(File.metadata_["match_status"].astext == "unsorted")
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
            #
            # B15 (2026-09-26): si el número que se está asignando viene de
            # un marcador de edición (Omnigold/Integral/Tomo/Vol) en el
            # nombre original, el Issue creado no es una grapa suelta —
            # re-parseamos ese nombre (todavía no reescrito, ver abajo) para
            # saberlo, en vez de fiarnos de metadata_ (que puede faltar en
            # archivos registrados antes de que existiera edition_kind).
            edition_kind = parse_comic_filename(file.file_name).edition_kind
            issue = Issue(
                series_id=series.id,
                issue_number=issue_number,
                locked_fields=["series_id", "issue_number"],
                format=_EDITION_KIND_A_FORMAT.get(edition_kind, IssueFormat.SINGLE_ISSUE),
            )
            self.db.add(issue)
            await self.db.flush()

        orig = Path(file.file_path)
        original_name = file.file_name  # capturado antes de reescribirlo abajo (B13: patrón de aprendizaje)
        dest = build_library_path(self._library, series, issue_number, orig.suffix)
        # A3: mover a destino verificado — nunca sobreescribe ni borra el
        # original hasta que la copia está completa (ver utils/fs.safe_move).
        final_dest = await safe_move_async(orig, dest)

        file.issue_id = issue.id
        file.file_path = str(final_dest)
        file.file_name = final_dest.name
        file.metadata_source = MetadataSource.MANUAL.value
        await self.db.flush()
        await self._learn_alias(original_name, series.id)
        return file

    async def _learn_alias(self, original_filename: str, series_id) -> None:
        """B13: cada asignación manual desde Pendientes es, por definición,
        una corrección — el matcher ya no supo resolverla solo (esa es la
        única razón por la que el archivo llegó a esta bandeja). Se
        aprende el patrón (título que naming.py extrae del nombre de
        archivo, normalizado) → serie, para que SeriesMatcher.decide()
        no vuelva a preguntar la próxima vez que aparezca. Una corrección
        más reciente sobre el mismo patrón sustituye a la anterior."""
        parsed = parse_comic_filename(original_filename)
        if not parsed.series:
            return
        pattern = normalize_title(parsed.series)
        if not pattern:
            return
        existing = (await self.db.execute(
            select(LocalAlias).where(LocalAlias.pattern_norm == pattern)
        )).scalar_one_or_none()
        if existing:
            existing.series_id = series_id
        else:
            self.db.add(LocalAlias(pattern_norm=pattern, series_id=series_id))
        await self.db.flush()

    async def dismiss(self, file_id) -> None:
        file = await self.db.get(File, file_id)
        if not file:
            raise ValueError("Archivo no encontrado")
        file.review_dismissed = True
        await self.db.flush()
