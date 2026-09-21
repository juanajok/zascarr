"""
Importador de archivos a la biblioteca.

Escanea dos fuentes de descargas:
  - Transmission: /media/DiscoDuro/downloads/comics
  - aMule:        /media/DiscoDuro/aMule/Incoming

Pipeline por archivo:
  1. SHA256 (deduplicación)
  2. Triage (capa 0): ComicInfo.xml + width_px + source_tag
  3. Matcher (capas 1-2): naming.py → pg_trgm
  4. Mover a /library/{tradición}/{Serie (Año)}/{Serie #NNN.ext}
  5. Registrar en tabla files
"""
from pathlib import Path
import shutil, structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.config import get_settings
from secuenciarr.models import File, FileFormat, Series
from secuenciarr.core.importer_triage import triage, TriageResult
from secuenciarr.core.matcher import SeriesMatcher, MatchStatus
from secuenciarr.utils.naming import parse_comic_filename

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

    async def scan_and_import(self) -> int:
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

        imported = 0
        for path in sorted(files):
            try:
                if await self._import_file(path):
                    imported += 1
            except Exception:
                logger.exception("importer.file_failed", path=str(path))
        return imported

    async def _import_file(self, path: Path) -> bool:
        tr: TriageResult = triage(path)

        # Deduplicación
        if tr.sha256:
            existing = (await self._db.execute(
                select(File).where(File.sha256_hash == tr.sha256)
            )).scalar_one_or_none()
            if existing:
                logger.info("importer.duplicate", path=str(path), hash=tr.sha256[:12])
                return False

        # Matching
        matcher = SeriesMatcher(self._db)

        def extractor(filename: str):
            p = parse_comic_filename(filename)
            if p.series and p.issue_number:
                return p.series, p.issue_number, p.year
            return None

        result = await matcher.decide(tr, extractor=extractor)

        # Determinar tradición y ruta destino
        tradition = "other"
        if result.series_id:
            series = (await self._db.execute(
                select(Series).where(Series.id == result.series_id)
            )).scalar_one_or_none()
            if series:
                tradition = series.tradition.value if series.tradition else "other"

        if result.status == MatchStatus.UNSORTED or not result.series_id:
            dest = self._library / "_Unsorted" / path.name
        else:
            series_obj = (await self._db.execute(
                select(Series).where(Series.id == result.series_id)
            )).scalar_one_or_none()
            dest = self._build_dest(series_obj, tr, path)

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(dest))

        file_rec = File(
            issue_id=str(result.issue_id) if result.issue_id else None,
            file_path=str(dest),
            file_name=dest.name,
            file_format=FileFormat(path.suffix.lstrip(".").lower()),
            file_size_bytes=dest.stat().st_size,
            sha256_hash=tr.sha256,
            source_tag=tr.source_tag,
            width_px=tr.width_px,
            covered_issue_ids=[],
            metadata_source="comicinfo_xml" if tr.strong_candidate else "manual",
            metadata_={
                "match_status": result.status,
                "match_score": result.score,
                "notes": result.notes,
            },
        )
        self._db.add(file_rec)
        await self._db.flush()
        logger.info("importer.imported", dest=str(dest), status=result.status)
        return True

    def _build_dest(self, series, tr: TriageResult, orig: Path) -> Path:
        if not series:
            return self._library / "_Unsorted" / orig.name

        tradition_folder = TRADITION_MAP.get(
            series.tradition.value if series.tradition else "other", "_Unsorted"
        )
        year_suffix = f" ({series.start_year})" if series.start_year else ""
        folder = f"{series.title}{year_suffix}"

        ci = tr.comic_info
        if ci and ci.number:
            num = ci.number.zfill(3)
            filename = f"{series.title} #{num}{orig.suffix}"
        else:
            filename = orig.name

        return self._library / tradition_folder / folder / filename
