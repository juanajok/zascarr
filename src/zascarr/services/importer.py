"""
Importador de archivos a la biblioteca.

Escanea dos fuentes de descargas:
  - Transmission: /media/downloads/comics
  - aMule:        /media/incoming

Pipeline por archivo:
  1. SHA256 (deduplicación)
  2. Triage (capa 0): ComicInfo.xml + width_px + source_tag
  3. Matcher (capas 1-2): naming.py → pg_trgm
  4. Mover a /library/{tradición}/{Serie (Año)}/{Serie #NNN.ext}
  5. Registrar en tabla files

Cada ciclo produce un ImportReport (B1/B3 del backlog): quién se importó,
quién se descartó por duplicado y de qué, quién quedó sin clasificar y por
qué. Se persiste en import_runs para poder responder "¿qué pasó en el
ciclo de las 03:00?" sin depender solo de los logs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.importer_triage import TriageResult, triage
from zascarr.core.matcher import MatchStatus, SeriesMatcher
from zascarr.models import File, FileFormat, ImportRun, Series
from zascarr.utils.fs import safe_move_async, sanitize_segment
from zascarr.utils.naming import parse_comic_filename

logger = structlog.get_logger()

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf", ".epub"}

TRADITION_MAP = {
    "american":       "Comics",
    "manga":          "Manga",
    "franco_belgian": "BD",
    "tebeo":          "Tebeos",
    "fumetti":        "Fumetti",
    "manhwa":         "Manhwa",
    "manhua":         "Manga",
    "british":        "Comics",
    "other":          "_Unsorted",
}


@dataclass
class ImportReport:
    """Resultado de un ciclo de scan_and_import(), en líneas legibles.

    Son cadenas ya formateadas, no datos estructurados: este informe está
    pensado para mostrarse tal cual (log, futura UI), no para consultarse
    campo a campo — para eso están los contadores (*_count en ImportRun).
    """
    started_at: datetime
    finished_at: datetime | None = None
    files_scanned: int = 0
    imported: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    unsorted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def imported_count(self) -> int:
        return len(self.imported)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)

    @property
    def unsorted_count(self) -> int:
        return len(self.unsorted)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class Importer:
    def __init__(self, db: AsyncSession):
        self._db = db
        s = get_settings()
        self._library = s.library_path
        self._scan_dirs = [
            Path(s.transmission_download_dir),
            Path(s.amule_incoming_dir),
            s.downloads_path,
        ]

    async def scan_and_import(self) -> ImportReport:
        report = ImportReport(started_at=datetime.now(UTC))

        files = []
        seen: set[str] = set()
        for d in self._scan_dirs:
            if not d.exists():
                continue
            for ext in COMIC_EXTS:
                for f in d.rglob(f"*{ext}"):
                    resolved = str(f.resolve())
                    if resolved not in seen:
                        seen.add(resolved)
                        files.append(f)
        report.files_scanned = len(files)

        for path in sorted(files):
            try:
                await self._import_file(path, report)
            except Exception as exc:
                logger.exception("importer.file_failed", path=str(path))
                report.errors.append(f"{path.name}: {exc}")

        report.finished_at = datetime.now(UTC)
        await self._persist_run(report)
        return report

    async def _import_file(self, path: Path, report: ImportReport) -> None:
        tr: TriageResult = triage(path)

        # Deduplicación
        if tr.sha256:
            existing = (await self._db.execute(
                select(File).where(File.sha256_hash == tr.sha256)
            )).scalar_one_or_none()
            if existing:
                report.duplicates.append(
                    f"{path.name} — duplicado de {existing.file_name}, descartado"
                )
                logger.info("importer.duplicate", path=str(path), hash=tr.sha256[:12])
                return

        # Matching
        matcher = SeriesMatcher(self._db)

        def extractor(filename: str):
            p = parse_comic_filename(filename)
            if p.series and p.issue_number:
                return p.series, p.issue_number, p.year
            return None

        result = await matcher.decide(tr, extractor=extractor)
        is_unsorted = result.status == MatchStatus.UNSORTED or not result.series_id

        # Determinar tradición y ruta destino
        if is_unsorted:
            dest = self._library / "_Unsorted" / path.name
        else:
            series_obj = (await self._db.execute(
                select(Series).where(Series.id == result.series_id)
            )).scalar_one_or_none()
            dest = self._build_dest(series_obj, tr, path)

        # A3: mover a destino verificado — nunca sobreescribe y no borra el
        # original hasta que la copia está completa (ver utils/fs.safe_move).
        final_dest = await safe_move_async(path, dest)

        file_rec = File(
            issue_id=str(result.issue_id) if result.issue_id else None,
            file_path=str(final_dest),
            file_name=final_dest.name,
            file_format=FileFormat(path.suffix.lstrip(".").lower()),
            file_size_bytes=final_dest.stat().st_size,
            sha256_hash=tr.sha256,
            source_tag=tr.source_tag,
            width_px=tr.width_px,
            covered_issue_ids=[],
            # 'manual' está reservado para correcciones humanas (nunca las
            # toca el enricher). Un match por naming.py es una heurística,
            # no una corrección: se deja en NULL para que el enricher pueda
            # completarlo más tarde. Solo ComicInfo.xml, que trae metadatos
            # estructurados de la propia release, se marca como fuente.
            metadata_source="comicinfo_xml" if tr.strong_candidate else None,
            metadata_={
                "match_status": result.status,
                "match_score": result.score,
                "notes": result.notes,
            },
        )
        self._db.add(file_rec)
        await self._db.flush()

        if is_unsorted:
            motivo = "; ".join(result.notes) or "sin match fiable"
            report.unsorted.append(f"{path.name} → _Unsorted ({motivo})")
        else:
            report.imported.append(f"{path.name} → {final_dest.relative_to(self._library)}")
        logger.info("importer.imported", dest=str(final_dest), status=result.status)

    async def _persist_run(self, report: ImportReport) -> None:
        run = ImportRun(
            started_at=report.started_at,
            finished_at=report.finished_at,
            files_scanned=report.files_scanned,
            imported_count=report.imported_count,
            duplicate_count=report.duplicate_count,
            unsorted_count=report.unsorted_count,
            error_count=report.error_count,
            details={
                "imported": report.imported,
                "duplicates": report.duplicates,
                "unsorted": report.unsorted,
                "errors": report.errors,
            },
        )
        self._db.add(run)
        await self._db.flush()

    def _build_dest(self, series, tr: TriageResult, orig: Path) -> Path:
        if not series:
            return self._library / "_Unsorted" / orig.name
        number = tr.comic_info.number if tr.comic_info else None
        return build_library_path(self._library, series, number, orig.suffix, fallback_name=orig.name)


def build_library_path(library: Path, series: Series, issue_number: str | None,
                       suffix: str, fallback_name: str | None = None) -> Path:
    """Ruta canónica /library/{tradición}/{Serie (Año)}/{Serie #NNN.ext}.

    Compartida entre el importer (issue_number viene de ComicInfo.xml, si
    lo hay) y ReviewService (B2: issue_number lo escribe el coleccionista
    a mano al asignar un archivo de _Unsorted). Sin número, se conserva el
    nombre de archivo original en vez de inventar uno.

    A3: `series.title` y `issue_number` son datos externos (ComicInfo.xml,
    fuentes de metadatos, escritura manual) y pueden traer "/", ".." o
    caracteres de control. Se sanitizan para que la ruta canónica NUNCA
    escape de la biblioteca — el destino siempre es verificable dentro de
    `library`.
    """
    tradition_folder = TRADITION_MAP.get(
        series.tradition.value if series.tradition else "other", "_Unsorted"
    )
    year_suffix = f" ({series.start_year})" if series.start_year else ""
    safe_title = sanitize_segment(series.title)
    folder = f"{safe_title}{year_suffix}"

    if issue_number:
        num = sanitize_segment(str(issue_number)).zfill(3)
        filename = f"{safe_title} #{num}{suffix}"
    else:
        filename = fallback_name or f"{safe_title}{suffix}"

    return library / tradition_folder / folder / filename
