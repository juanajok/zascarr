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
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID

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
    #: PREPARADOS en el lote en curso: mirados, pero sin confirmar en la BD. NO están en las listas de arriba:
    #: las listas (`registered`, `unsorted`, `duplicates`, `errors`) y `added_count` solo cuentan lo CONFIRMADO.
    pending_count: int = 0
    #: mirados cuyo lote NO se guardó (el commit falló y se comprobó que no quedó nada): no están añadidos
    reverted: int = 0
    #: mirados de un lote cuyo commit falló y NO se pudo comprobar si se guardó: pendiente de contrastar
    unknown: int = 0
    #: filas que este lote ha escrito en `files`, para acreditar con OTRA sesión si el commit se aplicó:
    #: (id de la fila, ruta nueva, ruta previa, ¿estaba desaparecida antes?). Fila CREADA → ruta previa `None` (su id
    #: solo existe si el commit se aplicó). Fila REENLAZADA (ya existía) → su estado previo completo (ruta y
    #: `is_missing`, que en una referencia obsoleta es False): «sigue como estaba» es ese estado, no otro.
    added_rows: list[tuple[UUID, str, str | None, bool]] = field(default_factory=list)

    def absorb(self, lote: AdoptionReport) -> None:
        """Pasa a este informe lo de un lote YA CONFIRMADO."""
        self.registered += lote.registered
        self.unsorted += lote.unsorted
        self.duplicates += lote.duplicates
        self.errors += lote.errors
        self.by_other_run += lote.by_other_run

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

        # Lo CONFIRMADO va en `report`; lo del lote en curso, en `en_lote`, y solo pasa a `report` cuando el
        # commit se acredita. Si el commit falla, el lote no se presenta como añadido.
        en_lote = AdoptionReport(started_at=report.started_at)
        confirmados = 0                   # archivos mirados cuyo lote ya está resuelto

        for n, path in enumerate(nuevos, start=1):
            try:
                if await self._ya_registrada(path):
                    # Otra ejecución (otra petición, otro proceso) la registró desde que se hizo la lista:
                    # consta, no se duplica y no es un error de esta.
                    en_lote.by_other_run += 1
                else:
                    async with self._db.begin_nested():
                        await self._adopt_file(path, en_lote, pistas.get(path.name))
            except IntegrityError as exc:
                if _restriccion(exc) == "files_file_path_key":      # la registró otra ejecución a la vez
                    en_lote.by_other_run += 1
                else:
                    logger.warning("library_adopter.file_failed", error=type(exc).__name__)
                    en_lote.errors.append(f"{path.name}: no se pudo registrar ({type(exc).__name__})")
            except Exception as exc:
                logger.warning("library_adopter.file_failed", error=type(exc).__name__)   # sin ruta ni mensaje (§5.4)
                en_lote.errors.append(f"{path.name}: no se pudo registrar ({type(exc).__name__})")
            report.processed = n
            report.pending_count = n - confirmados
            if progreso is not None:
                progreso(report)
            if n % lote == 0:
                await self._confirmar_lote(en_lote, report, n - confirmados, progreso)
                confirmados = n
                report.pending_count = 0
                en_lote = AdoptionReport(started_at=report.started_at)

        report.finished_at = datetime.now(UTC)
        # El informe que se guarda incluye el último lote, pero `report` solo lo incorpora si el commit se acredita.
        provisional = AdoptionReport(started_at=report.started_at, finished_at=report.finished_at,
                                     files_scanned=report.files_scanned,
                                     already_registered=report.already_registered, to_process=report.to_process,
                                     processed=report.processed)
        provisional.absorb(report)
        provisional.absorb(en_lote)
        run_id = await self._persist_run(provisional)
        # El marcador dice «el registro terminó». Con errores NO terminó: no se pone, y lo que
        # quedó sin registrar sigue a la vista (`inventario`) y se puede continuar repitiendo.
        if not provisional.errors:
            await RuntimeSettingsService(self._db).set_flag(_MARCADOR_HECHO, True)
        await self._confirmar_lote(en_lote, report, report.processed - confirmados, progreso, run_id)
        report.pending_count = 0
        return report

    async def _confirmar_lote(
        self, en_lote: AdoptionReport, report: AdoptionReport, mirados: int,
        progreso: Callable[[AdoptionReport], None] | None, run_id: UUID | None = None,
    ) -> None:
        """Confirma el lote y SOLO ENTONCES lo cuenta como añadido.

        Un `commit` que falla puede haber guardado el lote o no (p. ej. la conexión se cae tras enviarlo): no se
        asume ni una cosa ni la otra. Se acredita con OTRA sesión qué escribió ESTA transacción (ver
        `_contrastar`):
          · todo → se guardó (la respuesta se perdió): se cuenta y se sigue;
          · nada → se revirtió: el lote queda como «no guardado» y se propaga el fallo;
          · otra cosa, o no se puede preguntar → «por comprobar»: tampoco se cuenta, y se propaga el fallo.

        `run_id` es el informe (`ImportRun`) del cierre: el último commit guarda también el informe y el marcador,
        no solo filas de archivos, y debe poder acreditarse aunque el último lote no tenga ninguna fila.
        """
        try:
            await self._db.commit()
        except Exception as exc:
            logger.warning("library_adopter.commit_fallido", error=type(exc).__name__)
            with contextlib.suppress(Exception):
                await self._db.rollback()
            veredicto = await self._contrastar(en_lote.added_rows, run_id)
            if veredicto == "confirmado":
                report.absorb(en_lote)
                return
            if veredicto == "revertido":
                report.reverted += mirados
            else:
                report.unknown += mirados
            report.pending_count = 0
            if progreso is not None:
                progreso(report)
            raise
        report.absorb(en_lote)

    async def _contrastar(
        self, filas: list[tuple[UUID, str, str | None, bool]], run_id: UUID | None = None,
    ) -> str:
        """Con OTRA sesión: ¿se aplicó la transacción de ESTE lote? confirmado / revertido / desconocido.

        Se acredita por IDENTIDAD, no por presencia de rutas: que una ruta conste no prueba que la escribiera esta
        transacción (otro escritor pudo registrarla con otra fila tras el rollback). Se mira cada cosa que el commit
        debía escribir:
          · fila CREADA: existe SU id (nadie más puede tener un id generado en esta transacción) con SU ruta;
            si el id no existe, no se aplicó;
          · fila REENLAZADA: la fila ya existía, así que su id NO prueba autoría y su estado final esperado tampoco
            (otro escritor pudo hacer EXACTAMENTE el mismo reenlace). No es evidencia atribuible: solo sirve para
            afirmar que NO se aplicó (sigue en su estado previo) y para NO confirmar nada cuando es lo único que hay;
          · el informe del cierre (`ImportRun`), si lo hay: existe su id. Se guarda en la misma transacción que el
            marcador, así que acreditarlo acredita también el marcador.
        Cualquier otra combinación (una parte sí y otra no, una fila cambiada por otro) es «desconocido»: ni se
        cuenta como añadida ni como revertida. Sin nada que acreditar no hay nada que perder.
        """
        if not filas and run_id is None:
            return "confirmado"
        try:
            async with AsyncSession(self._db.bind, expire_on_commit=False) as otra:
                ids = [f[0] for f in filas]
                actuales = {}
                if ids:
                    for fid, ruta, falta in (await otra.execute(
                            select(File.id, File.file_path, File.is_missing).where(File.id.in_(ids)))).all():
                        actuales[fid] = (ruta, falta)
                informe = None
                if run_id is not None:
                    informe = (await otra.execute(select(ImportRun.id).where(ImportRun.id == run_id))).first()
        except Exception:  # noqa: BLE001 — ni siquiera se puede preguntar
            return "desconocido"
        # EVIDENCIA ATRIBUIBLE a esta transacción: las filas que CREÓ (su id solo existe si se aplicó) y su informe
        # del cierre. Un REENLACE de una fila que ya existía NO es atribuible: que la fila esté en el estado
        # esperado prueba que ALGUIEN lo aplicó, no que fuera esta transacción (otro escritor pudo hacer
        # exactamente el mismo reenlace tras el rollback; una sesión independiente ve lo confirmado por otros).
        atribuibles = aplicadas = no_aplicadas = 0
        reenlace_nuevo = reenlace_previo = reenlace_otro = 0
        for fid, ruta_nueva, ruta_previa, previa_ausente in filas:
            estado = actuales.get(fid)
            if ruta_previa is None:                               # creada por este lote
                atribuibles += 1
                if estado is None:
                    no_aplicadas += 1
                elif estado == (ruta_nueva, False):
                    aplicadas += 1
            elif estado == (ruta_nueva, False):                   # reenlazada: ya en el estado esperado
                reenlace_nuevo += 1
            elif estado == (ruta_previa, previa_ausente):          # sigue como estaba
                reenlace_previo += 1
            else:                                                 # en un tercer estado
                reenlace_otro += 1
        if run_id is not None:
            atribuibles += 1
            if informe is not None:
                aplicadas += 1
            else:
                no_aplicadas += 1
        reenlaces = reenlace_nuevo + reenlace_previo + reenlace_otro
        if reenlace_otro:
            return "desconocido"                                  # alguien más ha tocado la fila: no se adivina
        if atribuibles == 0:
            # Lote solo de reenlaces, sin recibo propio: el estado FINAL esperado no acredita autoría. Solo se
            # puede afirmar que NO se aplicó (todas siguen como estaban); cualquier otra cosa, por comprobar.
            return "revertido" if reenlaces and reenlace_previo == reenlaces else "desconocido"
        if aplicadas == atribuibles:                              # recibo propio presente → la transacción se aplicó
            return "confirmado" if reenlace_previo == 0 else "desconocido"
        if no_aplicadas == atribuibles:                           # recibo propio ausente → no se aplicó
            return "revertido" if reenlace_nuevo == 0 else "desconocido"
        return "desconocido"

    async def _adopt_file(
        self, path: Path, report: AdoptionReport, pista: PistaDeCohorte | None = None
    ) -> None:
        outcome = await _triage_and_match(self._db, path, pista)
        if outcome.recuperar is not None:
            # El fichero ya está en su sitio (la adopción nunca mueve): reenlaza
            # la fila desaparecida a ESTA ruta en vez de descartar. Si se
            # descartara, la fila seguiría `is_missing` y un fichero que el
            # coleccionista reorganizó quedaría sin registrar.
            ruta_previa, previa_ausente = outcome.recuperar.file_path, bool(outcome.recuperar.is_missing)
            await _reenlazar_fila(outcome.recuperar, outcome.tr, path)
            await self._db.flush()
            report.added_rows.append((outcome.recuperar.id, str(path), ruta_previa, previa_ausente))
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
        report.added_rows.append((file_rec.id, str(path), None, False))

        if is_unsorted:
            motivo = "; ".join(result.notes) or "sin match fiable"
            report.unsorted.append(f"{path.name} (pendiente de revisar) — {motivo}")
        else:
            report.registered.append(f"{path.name} — serie sugerida, falta confirmar número y edición")
        logger.info("library_adopter.registered", path=str(path), status=result.status)

    async def _persist_run(self, report: AdoptionReport) -> UUID:
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
        return run.id
