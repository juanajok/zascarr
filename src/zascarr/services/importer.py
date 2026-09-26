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

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.cohort import PistaDeCohorte, detectar_ordenes_de_lectura, quitar_prefijo_de_cohorte
from zascarr.core.importer_triage import TriageResult, triage
from zascarr.core.matcher import MatchResult, MatchStatus, SeriesHit, SeriesMatcher
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
    # B7: ficheros que YA estaban en la biblioteca y dejaron de existir en
    # disco desde el ciclo anterior (borrados a mano, fuera de ZascArr) —
    # no llegadas nuevas, eso es `imported`. `reappeared` es la reversión:
    # un fichero marcado desaparecido que ha vuelto a aparecer.
    disappeared: list[str] = field(default_factory=list)
    reappeared: list[str] = field(default_factory=list)

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
    def disappeared_count(self) -> int:
        return len(self.disappeared)

    @property
    def error_count(self) -> int:
        return len(self.errors)


@dataclass
class _Outcome:
    """Resultado de _triage_and_match: o bien un duplicado (con el nombre
    del File ya existente), o bien un MatchResult listo para decidir
    destino. Compartido entre Importer (mueve a la biblioteca) y
    LibraryAdopter (B11: registra en el sitio, nunca mueve) — es
    exactamente el mismo pipeline de triaje/deduplicación/matching en
    los dos casos; solo cambia qué se hace DESPUÉS del match."""
    tr: TriageResult
    result: MatchResult | None = None  # None si es un duplicado
    duplicate_of: str | None = None
    # Explicación de core/cohort.py (2026-09-26) SOLO si de verdad se usó
    # para este archivo — no si se calculó una pista que resultó ser un
    # no-op (formato ya cubierto por SORT_PREFIX_PATTERN). Se guarda en
    # metadata_ para que quede constancia en el informe del ciclo y en
    # la sugerencia de B12 ("¿es esta serie? — descartamos el 65 inicial
    # por evidencia de 38 archivos con el mismo patrón").
    cohorte_explicacion: str | None = None
    # B15 (2026-09-26): "omnigold"/"integral"/"tomo"/"volumen" cuando el
    # número viene de un marcador de edición y no de una grapa estándar
    # (naming.py::ParsedComicName.edition_kind). Se guarda en metadata_
    # para que ReviewService.assign_to_series sepa qué Issue.format poner
    # al confirmar la asignación, en vez de SINGLE_ISSUE por defecto.
    edition_kind: str | None = None


async def _triage_and_match(
    db: AsyncSession, path: Path, pista: PistaDeCohorte | None = None
) -> _Outcome:
    tr: TriageResult = triage(path)

    if tr.sha256:
        existing = (await db.execute(
            select(File).where(File.sha256_hash == tr.sha256)
        )).scalar_one_or_none()
        if existing:
            return _Outcome(tr=tr, result=None, duplicate_of=existing.file_name)

    matcher = SeriesMatcher(db)
    aplicada = False
    edition_kind: str | None = None

    def extractor(filename: str):
        nonlocal aplicada, edition_kind
        nombre = filename
        if pista is not None:
            nombre = quitar_prefijo_de_cohorte(filename, pista)
            aplicada = nombre != filename
        p = parse_comic_filename(nombre)
        edition_kind = p.edition_kind
        if p.series and p.issue_number:
            return p.series, p.issue_number, p.year
        return None

    result = await matcher.decide(tr, extractor=extractor)
    outcome = _Outcome(tr=tr, result=result, edition_kind=edition_kind)
    if aplicada:
        outcome.cohorte_explicacion = pista.explicacion
    return outcome


def serialize_candidates(candidates: list[SeriesHit]) -> list[dict]:
    """Candidatos de MatchResult a JSON plano para metadata_ (B12): la
    bandeja de Pendientes los lee para sugerir "¿es esta serie?" sin
    tener que rebuscar a mano. Guardados en orden de score descendente."""
    ordenados = sorted(candidates, key=lambda h: h.score, reverse=True)
    return [
        {
            "series_id": str(h.series_id),
            "title": h.title,
            "start_year": h.start_year,
            "score": h.score,
        }
        for h in ordenados
    ]


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
        # (st_dev, st_ino), no la ruta resuelta: HOST_DOWNLOADS_DIR y
        # HOST_AMULE_INCOMING_DIR pueden apuntar al mismo disco (caso normal,
        # no la excepción — bootstrap.sh los deja iguales cuando el usuario
        # da una sola carpeta de descargas), y entonces el mismo archivo
        # aparece bajo /media/downloads Y /media/incoming: dos bind-mounts
        # distintos del mismo inodo. Path.resolve() no lo detecta (son rutas
        # de verdad distintas dentro del contenedor); el inodo sí.
        seen: set[tuple[int, int]] = set()
        for d in self._scan_dirs:
            if not d.exists():
                continue
            for ext in COMIC_EXTS:
                for f in d.rglob(f"*{ext}"):
                    try:
                        st = f.stat()
                    except OSError:
                        continue
                    clave = (st.st_dev, st.st_ino)
                    if clave not in seen:
                        seen.add(clave)
                        files.append(f)
        report.files_scanned = len(files)

        # Evidencia de cohorte (core/cohort.py): calculada UNA VEZ sobre la
        # foto fija de este ciclo, antes del bucle — contrato de
        # determinismo (2026-09-26): un archivo que llega a mitad de ciclo
        # no puede cambiar la cohorte ya calculada para los anteriores.
        pistas = detectar_ordenes_de_lectura([f.name for f in files])

        for path in sorted(files):
            try:
                await self._import_file(path, report, pistas.get(path.name))
            except Exception as exc:
                logger.exception("importer.file_failed", path=str(path))
                report.errors.append(f"{path.name}: {exc}")

        # B7: revisión de la biblioteca YA importada, no de lo nuevo que
        # acaba de llegar — un paso independiente del bucle de arriba.
        try:
            report.disappeared, report.reappeared = await self._detectar_desaparecidos()
        except Exception:
            logger.exception("importer.deteccion_desaparecidos_fallida")

        report.finished_at = datetime.now(UTC)
        await self._persist_run(report)
        return report

    async def _detectar_desaparecidos(self) -> tuple[list[str], list[str]]:
        """B7: un tebeo borrado a mano del disco (fuera de ZascArr) deja
        de contar como "lo tienes" sin que nadie tenga que avisar.

        Guardarraíl crítico: si la carpeta de la biblioteca en sí parece
        inaccesible (disco de red desmontado, USB desconectado), NO se
        marca nada como desaparecido — confundir un problema de montaje
        con "he perdido toda mi colección" sería mucho peor que no
        detectar nada en este ciclo concreto. El siguiente ciclo, con el
        disco ya montado, no encontrará nada que marcar.
        """
        if not self._library.exists() or not self._library.is_dir():
            logger.warning(
                "importer.biblioteca_inaccesible_omitiendo_desaparecidos", ruta=str(self._library)
            )
            return [], []

        files = list((await self._db.execute(select(File))).scalars().all())
        rutas = [f.file_path for f in files]
        # Un único hop a un hilo para todo el lote, no uno por fichero —
        # Path.exists() es síncrono (I/O bloqueante, CLAUDE.md §4).
        ausentes = await asyncio.to_thread(lambda: {r for r in rutas if not Path(r).exists()})

        desaparecidos: list[str] = []
        reaparecidos: list[str] = []
        for f in files:
            ausente = f.file_path in ausentes
            if ausente and not f.is_missing:
                f.is_missing = True
                f.missing_since = datetime.now(UTC)
                desaparecidos.append(f.file_name)
            elif not ausente and f.is_missing:
                f.is_missing = False
                f.missing_since = None
                reaparecidos.append(f.file_name)

        if desaparecidos or reaparecidos:
            await self._db.flush()
        return desaparecidos, reaparecidos

    async def _import_file(
        self, path: Path, report: ImportReport, pista: PistaDeCohorte | None = None
    ) -> None:
        outcome = await _triage_and_match(self._db, path, pista)
        if outcome.duplicate_of:
            report.duplicates.append(f"{path.name} — duplicado de {outcome.duplicate_of}, descartado")
            logger.info("importer.duplicate", path=str(path), hash=outcome.tr.sha256[:12] if outcome.tr.sha256 else None)
            return
        tr, result = outcome.tr, outcome.result
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

        metadata: dict = {
            "match_status": result.status,
            "match_score": result.score,
            "notes": result.notes,
            "candidates": serialize_candidates(result.candidates),
        }
        if outcome.cohorte_explicacion:
            metadata["cohorte"] = outcome.cohorte_explicacion
        if outcome.edition_kind:
            metadata["edicion"] = outcome.edition_kind

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
            metadata_=metadata,
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
            disappeared_count=report.disappeared_count,
            details={
                "imported": report.imported,
                "duplicates": report.duplicates,
                "unsorted": report.unsorted,
                "errors": report.errors,
                "disappeared": report.disappeared,
                "reappeared": report.reappeared,
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
