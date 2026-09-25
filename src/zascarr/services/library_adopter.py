"""
LibraryAdopter — B11: adoptar una biblioteca ya organizada en el primer
arranque, sin mover ni renombrar nada.

A diferencia de Importer (que SÍ mueve archivos desde las carpetas de
descargas a su sitio canónico), aquí los archivos YA están donde el
coleccionista los puso — moverlos sería el mismo error que H5 de A3 ya
evita en el instalador ("nunca se re-propietan los tebeos que el usuario
ya tenía"), solo que sobre la biblioteca en vez de sobre la instalación.
Reutiliza el mismo pipeline de triaje/deduplicación/matching que Importer
(`services.importer._triage_and_match`); la única diferencia real es que
`file_path` es la ruta ACTUAL del archivo, nunca un destino calculado.

Un archivo sin match fiable se registra igualmente (issue_id=None) en
vez de moverse a `_Unsorted/` — aparece en la bandeja de Pendientes
(B2) tal cual, en su sitio real, para que el coleccionista lo clasifique
a mano si quiere; StreamService.assign_to_series ya sabe mover un
archivo desde donde esté cuando el coleccionista confirma una serie.

Disparo automático (ver main.py::lifespan): solo si `library_path` tiene
al menos un cómic Y la tabla `series` está vacía — pero solo la PRIMERA
vez. Sin un marcador aparte, si todo el escaneo inicial queda sin
clasificar (series sigue en 0), el disparador se repetiría en cada
reinicio, releyendo toda la biblioteca cada vez. El marcador vive en
`runtime_settings` (una clave interna, `_library_adoption_done`, fuera
de `OVERRIDABLE_FIELDS` — nunca editable desde /ui/ajustes).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.cohort import PistaDeCohorte, detectar_ordenes_de_lectura
from zascarr.core.matcher import MatchStatus
from zascarr.models import File, FileFormat, ImportRun, Series
from zascarr.services.importer import COMIC_EXTS, _triage_and_match, serialize_candidates

logger = structlog.get_logger()

_MARCADOR_HECHO = "_library_adoption_done"


@dataclass
class AdoptionReport:
    """Mismo espíritu que ImportReport (B1/B3): líneas legibles, no datos
    estructurados — se persiste en import_runs con kind="adoption" para
    distinguirlo de un ciclo normal de descargas."""
    started_at: datetime
    finished_at: datetime | None = None
    files_scanned: int = 0
    registered: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    unsorted: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def registered_count(self) -> int:
        return len(self.registered)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)

    @property
    def unsorted_count(self) -> int:
        return len(self.unsorted)

    @property
    def error_count(self) -> int:
        return len(self.errors)


class LibraryAdopter:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._library: Path = get_settings().library_path

    async def should_run(self) -> bool:
        """Condición del disparo automático (ver docstring del módulo):
        biblioteca con contenido, catálogo vacío, y no se ha adoptado ya
        antes — comprobado en ese orden porque el marcador y el conteo de
        `series` son consultas baratas, listar la biblioteca no lo es."""
        from zascarr.services.runtime_settings import RuntimeSettingsService

        if await RuntimeSettingsService(self._db).get_flag(_MARCADOR_HECHO):
            return False
        total_series = (await self._db.execute(select(func.count(Series.id)))).scalar() or 0
        if total_series > 0:
            return False
        if not self._library.exists():
            return False
        return self._primer_comic() is not None

    def _primer_comic(self) -> Path | None:
        for ext in COMIC_EXTS:
            try:
                return next(self._library.rglob(f"*{ext}"))
            except StopIteration:
                continue
        return None

    async def adopt(self) -> AdoptionReport:
        from zascarr.services.runtime_settings import RuntimeSettingsService

        report = AdoptionReport(started_at=datetime.now(UTC))

        files: list[Path] = []
        seen: set[tuple[int, int]] = set()
        for ext in COMIC_EXTS:
            for f in self._library.rglob(f"*{ext}"):
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
        # foto fija de esta pasada — mismo contrato de determinismo que
        # Importer.scan_and_import.
        pistas = detectar_ordenes_de_lectura([f.name for f in files])

        for path in sorted(files):
            try:
                await self._adopt_file(path, report, pistas.get(path.name))
            except Exception as exc:
                logger.exception("library_adopter.file_failed", path=str(path))
                report.errors.append(f"{path.name}: {exc}")

        report.finished_at = datetime.now(UTC)
        await self._persist_run(report)
        # Se marca "hecho" pase lo que pase (incluso 0 registrados): el
        # objetivo es no repetir el escaneo completo, no garantizar éxito.
        await RuntimeSettingsService(self._db).set_flag(_MARCADOR_HECHO, True)
        return report

    async def _adopt_file(
        self, path: Path, report: AdoptionReport, pista: PistaDeCohorte | None = None
    ) -> None:
        outcome = await _triage_and_match(self._db, path, pista)
        if outcome.duplicate_of:
            report.duplicates.append(f"{path.name} — duplicado de {outcome.duplicate_of}, descartado")
            return
        tr, result = outcome.tr, outcome.result
        is_unsorted = result.status == MatchStatus.UNSORTED or not result.series_id

        metadata: dict = {
            "match_status": result.status,
            "match_score": result.score,
            "notes": result.notes,
            "adopted": True,
            "candidates": serialize_candidates(result.candidates),
        }
        if outcome.cohorte_explicacion:
            metadata["cohorte"] = outcome.cohorte_explicacion

        # Nunca se mueve: file_path es la ruta real donde el coleccionista
        # ya tenía el archivo, no un destino calculado (a diferencia de
        # Importer._import_file).
        file_rec = File(
            issue_id=str(result.issue_id) if result.issue_id else None,
            file_path=str(path),
            file_name=path.name,
            file_format=FileFormat(path.suffix.lstrip(".").lower()),
            file_size_bytes=path.stat().st_size,
            sha256_hash=tr.sha256,
            source_tag=tr.source_tag,
            width_px=tr.width_px,
            covered_issue_ids=[],
            metadata_source="comicinfo_xml" if tr.strong_candidate else None,
            metadata_=metadata,
        )
        self._db.add(file_rec)
        await self._db.flush()

        if is_unsorted:
            motivo = "; ".join(result.notes) or "sin match fiable"
            report.unsorted.append(f"{path.name} (pendiente de revisar) — {motivo}")
        else:
            report.registered.append(f"{path.name} — serie ya identificada")
        logger.info("library_adopter.registered", path=str(path), status=result.status)

    async def _persist_run(self, report: AdoptionReport) -> None:
        run = ImportRun(
            started_at=report.started_at,
            finished_at=report.finished_at,
            files_scanned=report.files_scanned,
            imported_count=report.registered_count,
            duplicate_count=report.duplicate_count,
            unsorted_count=report.unsorted_count,
            error_count=report.error_count,
            details={
                "kind": "adoption",
                "registered": report.registered,
                "duplicates": report.duplicates,
                "unsorted": report.unsorted,
                "errors": report.errors,
            },
        )
        self._db.add(run)
        await self._db.flush()
