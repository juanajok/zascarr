# ruff: noqa: E501
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

REGISTRO EXPLÍCITO CON CATÁLOGO PREVIO (2026-10-05): crear algunas series antes de
registrar la biblioteca no puede impedir incorporar los archivos que ya se tienen. La
condición «catálogo vacío» sigue siendo la del disparo AUTOMÁTICO (`should_run`, que
solo arranca el análisis de solo lectura); con catálogo previo el registro es una acción
CONSCIENTE (`puede_registrar`): se previsualiza (`inventario`, sin leer contenido), se
confirma a mano, no toca las series ni los enlaces existentes y es idempotente por ruta
(repetirlo no duplica nada). Cada lote se confirma en la BD; el marcador de «hecho» solo
se pone si el registro terminó sin errores, para no esconder lo que quedó pendiente.

Disparo automático (ver main.py::lifespan): solo si `library_path` tiene
al menos un cómic Y la tabla `series` está vacía — pero solo la PRIMERA
vez. Sin un marcador aparte, si todo el escaneo inicial queda sin
clasificar (series sigue en 0), el disparador se repetiría en cada
reinicio, releyendo toda la biblioteca cada vez. El marcador vive en
`runtime_settings` (una clave interna, `_library_adoption_done`, fuera
de `OVERRIDABLE_FIELDS` — nunca editable desde /ui/ajustes).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.cohort import PistaDeCohorte, detectar_ordenes_de_lectura
from zascarr.core.matcher import MatchStatus
from zascarr.models import File, FileFormat, ImportRun, Series
from zascarr.services.asignacion import _restriccion
from zascarr.services.importer import (
    COMIC_EXTS,
    _reenlazar_fila,
    _triage_and_match,
    serialize_candidates,
)
from zascarr.utils.fs import listar_comics

logger = structlog.get_logger()

_MARCADOR_HECHO = "_library_adoption_done"
#: cuántos archivos se registran entre confirmaciones en la BD
_LOTE_POR_DEFECTO = 25


class EstadoAdopcion(StrEnum):
    """Dónde está la adopción (B11), observado y no supuesto."""
    PENDIENTE = "pendiente"              # hay tebeos en la biblioteca, catálogo vacío, sin adoptar
    HECHA = "hecha"                      # ya se ejecutó (marcador): aunque registrara 0
    CATALOGO_PREVIO = "catalogo_previo"  # ya hay series sin haber adoptado: no se ofrece
    SIN_TEBEOS = "sin_tebeos"            # la carpeta no existe o no contiene ningún cómic


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
    #: archivos cuya ruta ya estaba registrada: no se tocan (la adopción es idempotente por ruta)
    already_registered: int = 0
    #: a cuántos archivos NUEVOS se les ha dado ya una respuesta (registrado / repetido / error / de otra ejecución)
    processed: int = 0
    #: archivos que otra ejecución registró mientras esta corría (solape): ya constan, no son un error
    by_other_run: int = 0
    #: cuántos archivos nuevos había al empezar (el denominador del progreso)
    to_process: int = 0

    @property
    def registered_count(self) -> int:
        return len(self.registered)

    @property
    def added_count(self) -> int:
        """Filas REALMENTE añadidas al catálogo en esta ejecución (reconocidos + sin identificar). Distinto de
        `processed`: un archivo procesado puede haber sido un repetido, un error o de otra ejecución."""
        return len(self.registered) + len(self.unsorted)

    @property
    def duplicate_count(self) -> int:
        return len(self.duplicates)

    @property
    def unsorted_count(self) -> int:
        return len(self.unsorted)

    @property
    def error_count(self) -> int:
        return len(self.errors)


@dataclass(frozen=True)
class InventarioBiblioteca:
    """Lo que hay en la carpeta frente a lo que ZascArr ya conoce. Se calcula SIN leer el contenido de los
    archivos (solo nombres y rutas): es barato y se puede enseñar antes de pedir confirmación. «Nuevos» sale de
    cruzar las rutas con las ya registradas, no de restar totales."""
    en_disco: int
    cbz: int
    cbr: int
    otros_formatos: int
    ya_registrados: int
    nuevos: int
    registrados_sin_fichero: int   # filas bajo la biblioteca cuyo archivo ya no está: hay que revisarlas

    @property
    def hay_que_registrar(self) -> bool:
        return self.nuevos > 0


class LibraryAdopter:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._library: Path = get_settings().library_path

    async def estado(self) -> EstadoAdopcion:
        """Por qué la adopción corre o no (V4: el Inicio necesita distinguirlo; `should_run` solo
        dice sí/no). Comprobado en este orden porque el marcador y el conteo de `series` son
        consultas baratas y listar la biblioteca no lo es."""
        from zascarr.services.runtime_settings import RuntimeSettingsService

        if await RuntimeSettingsService(self._db).get_flag(_MARCADOR_HECHO):
            return EstadoAdopcion.HECHA
        total_series = (await self._db.execute(select(func.count(Series.id)))).scalar() or 0
        # E/S de disco (en red, cada llamada es una ida y vuelta): a un hilo. Se mira ANTES de decidir
        # CATALOGO_PREVIO: con catálogo previo solo se ofrece el registro si hay tebeos que registrar.
        if not await asyncio.to_thread(self._library.exists):
            return EstadoAdopcion.SIN_TEBEOS
        if await asyncio.to_thread(self._primer_comic) is None:
            return EstadoAdopcion.SIN_TEBEOS
        if total_series > 0:
            return EstadoAdopcion.CATALOGO_PREVIO
        return EstadoAdopcion.PENDIENTE

    async def should_run(self) -> bool:
        """Condición del disparo AUTOMÁTICO (ver docstring del módulo): biblioteca con contenido,
        catálogo vacío, y no se ha adoptado ya antes. Con catálogo previo NO arranca nada solo."""
        return await self.estado() is EstadoAdopcion.PENDIENTE

    async def puede_registrar(self) -> bool:
        """¿Se ofrece el registro explícito? Hay tebeos visibles y no consta un registro completo,
        HAYA O NO catálogo previo. Es lo que decide la interfaz; no dispara nada."""
        return await self.estado() in (EstadoAdopcion.PENDIENTE, EstadoAdopcion.CATALOGO_PREVIO)

    async def _ya_registrada(self, path: Path) -> bool:
        """¿Consta ya esta ruta? Se vuelve a preguntar por archivo: la lista de «nuevos» es una foto de
        antes de empezar y otra ejecución puede haberla adelantado."""
        fila = await self._db.execute(select(File.id).where(File.file_path == str(path)).limit(1))
        return fila.first() is not None

    async def _rutas_registradas(self) -> set[str]:
        filas = await self._db.execute(select(File.file_path))
        return {str(r) for r in filas.scalars().all()}

    async def inventario(self) -> InventarioBiblioteca:
        """Qué hay en la carpeta frente a lo ya registrado, sin leer el contenido de ningún archivo."""
        archivos = await asyncio.to_thread(listar_comics, [self._library], COMIC_EXTS)
        registradas = await self._rutas_registradas()
        en_disco = {str(a) for a in archivos}
        prefijo = str(self._library).rstrip("/") + "/"
        return InventarioBiblioteca(
            en_disco=len(archivos),
            cbz=sum(1 for a in archivos if a.suffix.lower() == ".cbz"),
            cbr=sum(1 for a in archivos if a.suffix.lower() == ".cbr"),
            otros_formatos=sum(1 for a in archivos if a.suffix.lower() not in (".cbz", ".cbr")),
            ya_registrados=sum(1 for a in en_disco if a in registradas),
            nuevos=sum(1 for a in en_disco if a not in registradas),
            registrados_sin_fichero=sum(
                1 for r in registradas if r.startswith(prefijo) and r not in en_disco),
        )

    def _primer_comic(self) -> Path | None:
        for ext in COMIC_EXTS:
            try:
                return next(self._library.rglob(f"*{ext}"))
            except StopIteration:
                continue
        return None

    async def adopt(
        self, *, progreso: Callable[[AdoptionReport], None] | None = None, lote: int = _LOTE_POR_DEFECTO,
    ) -> AdoptionReport:
        """Registra, sin mover nada, los archivos cuya RUTA aún no está en el catálogo.

        - **Idempotente por ruta**: lo ya registrado se cuenta y no se toca; repetir la acción continúa
          donde se quedó (tras un fallo, un corte o un error en algunos archivos) y no duplica filas.
        - **Cada archivo en su savepoint**: un fallo no deja la sesión inservible para los siguientes.
        - **Cada lote se confirma** (`commit`): lo hecho sobrevive a un corte, no se pierde todo por el
          último. `progreso` se llama tras cada archivo.
        - **El marcador de «hecho» solo se pone si no hubo errores.** Con errores queda sin poner y el
          estado sigue ofreciendo continuar; un marcador no puede esconder lo pendiente.
        """
        from zascarr.services.runtime_settings import RuntimeSettingsService

        report = AdoptionReport(started_at=datetime.now(UTC))

        # Dedupe por inodo y recorrido en un hilo: ver `listar_comics`.
        files = await asyncio.to_thread(listar_comics, [self._library], COMIC_EXTS)
        report.files_scanned = len(files)
        registradas = await self._rutas_registradas()
        nuevos = sorted(f for f in files if str(f) not in registradas)
        report.already_registered = len(files) - len(nuevos)
        report.to_process = len(nuevos)

        # Evidencia de cohorte (core/cohort.py): calculada UNA VEZ sobre la
        # foto fija de esta pasada — mismo contrato de determinismo que
        # Importer.scan_and_import. Se calcula sobre TODOS los nombres: la evidencia de
        # «este prefijo varía» necesita ver también los archivos ya registrados.
        pistas = detectar_ordenes_de_lectura([f.name for f in files])
        if progreso is not None:
            progreso(report)        # ya se sabe cuántos hay: la barra puede tener su total desde el principio

        for n, path in enumerate(nuevos, start=1):
            try:
                if await self._ya_registrada(path):
                    # Otra ejecución (otra petición, otro proceso) la registró desde que se hizo la lista:
                    # consta, no se duplica y no es un error de esta.
                    report.by_other_run += 1
                else:
                    async with self._db.begin_nested():
                        await self._adopt_file(path, report, pistas.get(path.name))
            except IntegrityError as exc:
                if _restriccion(exc) == "files_file_path_key":      # la registró otra ejecución a la vez
                    report.by_other_run += 1
                else:
                    logger.warning("library_adopter.file_failed", error=type(exc).__name__)
                    report.errors.append(f"{path.name}: no se pudo registrar ({type(exc).__name__})")
            except Exception as exc:
                logger.warning("library_adopter.file_failed", error=type(exc).__name__)   # sin ruta ni mensaje (§5.4)
                report.errors.append(f"{path.name}: no se pudo registrar ({type(exc).__name__})")
            report.processed = n
            if progreso is not None:
                progreso(report)
            if n % lote == 0:
                await self._db.commit()

        report.finished_at = datetime.now(UTC)
        await self._persist_run(report)
        # El marcador dice «el registro terminó». Con errores NO terminó: no se pone, y lo que
        # quedó sin registrar sigue a la vista (`inventario`) y se puede continuar repitiendo.
        if not report.errors:
            await RuntimeSettingsService(self._db).set_flag(_MARCADOR_HECHO, True)
        await self._db.commit()
        return report

    async def _adopt_file(
        self, path: Path, report: AdoptionReport, pista: PistaDeCohorte | None = None
    ) -> None:
        outcome = await _triage_and_match(self._db, path, pista)
        if outcome.recuperar is not None:
            # El fichero ya está en su sitio (la adopción nunca mueve): reenlaza
            # la fila desaparecida a ESTA ruta en vez de descartar. Si se
            # descartara, la fila seguiría `is_missing` y un fichero que el
            # coleccionista reorganizó quedaría sin registrar.
            await _reenlazar_fila(outcome.recuperar, outcome.tr, path)
            await self._db.flush()
            report.registered.append(f"{path.name} — reenlazado (recuperado)")
            logger.info("library_adopter.reenlazado", path=str(path))
            return
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
        if outcome.edition_kind:
            metadata["edicion"] = outcome.edition_kind

        # Nunca se mueve: file_path es la ruta real donde el coleccionista
        # ya tenía el archivo, no un destino calculado (a diferencia de
        # Importer._import_file).
        file_rec = File(
            issue_id=str(result.issue_id) if result.issue_id else None,
            file_path=str(path),
            file_name=path.name,
            file_format=FileFormat(path.suffix.lstrip(".").lower()),
            file_size_bytes=(await asyncio.to_thread(path.stat)).st_size,
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
                "already_registered": report.already_registered,
                "by_other_run": report.by_other_run,
            },
        )
        self._db.add(run)
        await self._db.flush()
