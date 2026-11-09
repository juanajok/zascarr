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
import hashlib
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
from zascarr.core.cohort import (
    PistaDeCohorte,
    detectar_ordenes_de_lectura,
    quitar_prefijo_de_cohorte,
)
from zascarr.core.matcher import MatchStatus, normalize_title
from zascarr.models import File, FileFormat, ImportRun, Issue, Series
from zascarr.services.asignacion import _restriccion
from zascarr.services.discrepancias import (
    ORIGEN_COMICINFO,
    ORIGEN_RESCAN,
    Propuesta,
    crear_discrepancia,
    marcar_estado_por_relacion,
    registrar,
)
from zascarr.services.importer import (
    COMIC_EXTS,
    CerrojoDeContenidoOcupado,
    Importer,
    _fichero_de_la_fila_existe,
    _reenlazar_fila,
    _triage_and_match,
    serialize_candidates,
)
from zascarr.services.relacion_confirmada import (
    es_protegida,
    estado_de_relacion,
    relacion_actual,
)
from zascarr.utils.bloqueo_archivo import bloquear_archivo
from zascarr.utils.fs import recorrer_comics
from zascarr.utils.naming import parse_comic_filename

logger = structlog.get_logger()

_MARCADOR_HECHO = "_library_adoption_done"
#: cuántos archivos se registran entre confirmaciones en la BD
_LOTE_POR_DEFECTO = 25


class ArchivoCambiado(Exception):  # noqa: N818  (nombre de dominio en español, como el resto del proyecto)
    """El archivo cambió (tamaño o fecha) mientras se leía para registrarlo: el hash leído ya no describe lo que hay en disco."""


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
    #: #326: filas que ya existían (desaparecidas) y se REENLAZARON a esta ruta. También constan en `registered` (compatibilidad);
    #: aquí se cuentan aparte porque un reenlace no crea una fila nueva.
    relinked: int = 0
    #: #326 (solo registro incremental): su contenido coincide con VARIAS filas desaparecidas y no hay una elección inequívoca:
    #: no se reenlaza ninguna, no se crea fila y se informa para que decida una persona.
    ambiguous: list[str] = field(default_factory=list)
    #: #326 (solo registro incremental): archivos del alcance confirmado que NO se trataron, cada uno con su causa: ya no estaban pendientes al
    #: empezar (desaparecieron o ya constaban) o desaparecieron antes de leerlos. No son errores, pero tampoco quedan registrados: constan aquí.
    omitted: list[str] = field(default_factory=list)
    #: de los `omitted`, los que desaparecieron DURANTE el recorrido (están contados en `processed`; los de antes de empezar, no)
    vanished: int = 0
    #: #332 (residual 2 de #329): carpetas o archivos que el recorrido NO pudo leer (`Recorrido.ilegibles`). Con `> 0` el recorrido no acredita haber
    #: visto toda la biblioteca: la ejecución no se da por completa, no pone el marcador de «hecho» y lo dice, igual que la búsqueda del incremental.
    unreadable: int = 0

    @property
    def out_of_scope_gone(self) -> int:
        return len(self.omitted)

    def absorb(self, lote: AdoptionReport) -> None:
        """Pasa a este informe lo de un lote YA CONFIRMADO."""
        self.registered += lote.registered
        self.unsorted += lote.unsorted
        self.duplicates += lote.duplicates
        self.errors += lote.errors
        self.by_other_run += lote.by_other_run
        self.relinked += lote.relinked
        self.ambiguous += lote.ambiguous
        self.omitted += lote.omitted
        self.vanished += lote.vanished

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


@dataclass
class RescanReport:
    """BL-R9: informe honesto del rescan de la biblioteca, por categorías.

    «Revisados» no es «cambiados»: lo que quedó igual no se toca (ni se abre), lo que cambió
    se re-tría, lo nuevo se registra (identificado → serie; si no → «Por revisar»), lo
    desaparecido se marca (B7, sin borrar nunca la fila). Con un recorrido incompleto
    (`no_revisado`), nada se afirma como «sin cambios».
    """
    started_at: datetime
    disparador: str = "manual"       # «manual» (botón) o «automatico» (cadencia)
    finished_at: datetime | None = None
    files_scanned: int = 0           # rutas recorridas en la biblioteca
    unreadable: int = 0              # carpetas/archivos que no se pudieron leer (recorrido incompleto)
    no_revisado: bool = False        # el recorrido no acredita haber visto toda la biblioteca
    ya_registrados: int = 0          # rutas con fila en el catálogo
    sin_cambios: int = 0             # rutas con fila y stat igual: no se abrió el CBZ
    nuevos_entregados: int = 0       # rutas sin fila entregadas al registro (alcance de adopt)
    nuevos_registrados: int = 0      # filas nuevas identificadas (a su serie)
    nuevos_a_revisar: int = 0        # filas nuevas sin identificar → «Por revisar»
    repetidos: int = 0               # rutas sin fila cuyo contenido ya estaba (copias: no se registran)
    reenlazados: int = 0             # filas desaparecidas reenlazadas a una ruta nueva (movidos)
    ambiguos: list[str] = field(default_factory=list)
    re_triados: int = 0              # rutas con fila cuyo stat cambió (o línea de base): re-leídas
    re_triados_igual: int = 0        #   mismo contenido o misma publicación: stat/hash actualizados
    re_triados_cambiado: int = 0     #   ahora es otra publicación: vínculo actualizado
    re_triados_a_revisar: int = 0    #   ya no se identifica: desvinculada → «Por revisar»
    re_triados_descartado: int = 0   #   descartada a mano: solo el stat, no se reactiva (regla #326)
    copias_de_otra: int = 0          #   ahora es copia idéntica de otra fila presente: vínculo conservado
    re_triados_protegidos: int = 0   # #233/BL-R4: relación confirmada/manual protegida, no se cambió el vínculo
    discrepancias_registradas: int = 0  # #233/BL-R4: propuestas distintas registradas (deduplicadas por clave)
    errores: list[str] = field(default_factory=list)
    omitidos: list[str] = field(default_factory=list)
    por_comprobar: int = 0           # re-triajes cuyo commit no se pudo acreditar (el siguiente rescan los revisa)
    desaparecidos: int = 0
    reaparecidos: int = 0
    resultado_biblioteca: str = ""   # del _comprobar_biblioteca (comprobada / raiz_* / desaparicion_masiva)
    run_id: UUID | None = None


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
    #: #326: la carpeta de la biblioteca existe y es legible. Si no, «0 nuevos» no significa «no hay nada nuevo»: no se vio nada.
    carpeta_accesible: bool = True
    #: #326: cuántas carpetas o archivos NO se pudieron leer al recorrer. Con `> 0` el recorrido es INCOMPLETO: no acredita haber visto toda la
    #: biblioteca, así que no se ofrece una confirmación global ni se cuentan «registrados sin fichero» (sería fabricar bajas).
    ilegibles: int = 0
    #: #326: las rutas NUEVAS vistas (alcance de una confirmación). No se compara ni se imprime.
    rutas_nuevas: frozenset[str] = field(default=frozenset(), repr=False, compare=False)

    @property
    def hay_que_registrar(self) -> bool:
        return self.nuevos > 0

    @property
    def recorrido_completo(self) -> bool:
        return self.carpeta_accesible and self.ilegibles == 0

    @property
    def se_puede_confirmar(self) -> bool:
        """Solo se confirma un registro global si se acredita haber visto TODA la carpeta."""
        return self.recorrido_completo and self.hay_que_registrar

    @property
    def huella(self) -> str:
        """Resumen estable de QUÉ rutas nuevas se enseñaron (solo nombres, ningún archivo se lee). La confirmación la lleva consigo:
        si al confirmar la carpeta ya no da la misma huella, no se registra nada y se vuelve a enseñar lo que hay ahora."""
        return hashlib.sha256("\n".join(sorted(self.rutas_nuevas)).encode()).hexdigest()


def _clave_de_orden_de_retriaje(fila_y_ruta: tuple) -> str:
    """Orden GLOBAL de re-triaje por `File.id` (mismo que el tagger).

    Los advisory locks se retienen hasta el commit del lote; si el tagger y el
    rescan piden los locks de varios ficheros en órdenes distintos (tagger por
    `imported_at,id`, rescan por ruta), dos procesos pueden tomar A/B al revés
    y bloquearse mutuamente. Ordenar ambos por `File.id` elimina el ciclo.
    """
    return str(fila_y_ruta[1].id)


class LibraryAdopter:
    def __init__(self, db: AsyncSession):
        self._db = db
        self._library: Path = get_settings().library_path
        self._incremental = False      # #326: lo fija `adopt(alcance=...)`; cambia cómo se trata una coincidencia ambigua de contenido

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

    async def ofrece_registro_incremental(self) -> bool:
        """#326: ¿se ofrece buscar y registrar archivos NUEVOS? Solo cuando el registro inicial ya consta (marcador): antes de eso
        la oferta es el registro completo (`puede_registrar`). No lee el disco ni escribe nada. El marcador no se toca nunca desde aquí."""
        return await self.estado() is EstadoAdopcion.HECHA

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
        recorrido = await asyncio.to_thread(recorrer_comics, [self._library], COMIC_EXTS)
        archivos = recorrido.archivos
        registradas = await self._rutas_registradas()
        en_disco = {str(a) for a in archivos}
        prefijo = str(self._library).rstrip("/") + "/"
        accesible = await asyncio.to_thread(self._library.is_dir)
        return InventarioBiblioteca(
            carpeta_accesible=accesible,
            ilegibles=recorrido.ilegibles,
            rutas_nuevas=frozenset(a for a in en_disco if a not in registradas),
            en_disco=len(archivos),
            cbz=sum(1 for a in archivos if a.suffix.lower() == ".cbz"),
            cbr=sum(1 for a in archivos if a.suffix.lower() == ".cbr"),
            otros_formatos=sum(1 for a in archivos if a.suffix.lower() not in (".cbz", ".cbr")),
            ya_registrados=sum(1 for a in en_disco if a in registradas),
            nuevos=sum(1 for a in en_disco if a not in registradas),
            # Con un recorrido incompleto «no la veo» no es «ya no está»: no se fabrican bajas.
            registrados_sin_fichero=0 if recorrido.ilegibles else sum(
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
        alcance: frozenset[str] | None = None,
    ) -> AdoptionReport:
        """Registra, sin mover nada, los archivos cuya RUTA aún no está en el catálogo.

        - **Idempotente por ruta**: lo ya registrado se cuenta y no se toca; repetir la acción continúa
          donde se quedó (tras un fallo, un corte o un error en algunos archivos) y no duplica filas.
        - **Cada archivo en su savepoint**: un fallo no deja la sesión inservible para los siguientes.
        - **Cada lote se confirma** (`commit`): lo hecho sobrevive a un corte, no se pierde todo por el
          último. `progreso` se llama tras cada archivo.
        - **El marcador de «hecho» solo se pone si no hubo errores.** Con errores queda sin poner y el
          estado sigue ofreciendo continuar; un marcador no puede esconder lo pendiente.

        #326, registro INCREMENTAL: con `alcance` (las rutas que la persona vio y confirmó) solo se tratan esas rutas, aunque hayan
        aparecido más después; el marcador no se toca y el informe se guarda con otro `kind` (no pisa el de la adopción inicial).
        """
        from zascarr.services.runtime_settings import RuntimeSettingsService

        report = AdoptionReport(started_at=datetime.now(UTC))

        # Dedupe por inodo y recorrido en un hilo: ver `recorrer_comics`.
        recorrido = await asyncio.to_thread(recorrer_comics, [self._library], COMIC_EXTS)
        files = recorrido.archivos
        report.unreadable = recorrido.ilegibles
        report.files_scanned = len(files)
        registradas = await self._rutas_registradas()
        nuevos = sorted(f for f in files if str(f) not in registradas)
        report.already_registered = len(files) - len(nuevos)
        incremental = self._incremental = alcance is not None
        if incremental:
            ahora = {str(f) for f in nuevos}
            causa = ("ya no estaba pendiente al empezar (desapareció o ya constaba)" if not report.unreadable
                     else "no se vio al empezar: desapareció, ya constaba o su carpeta no se pudo leer")
            report.omitted = [f"{Path(r).name} — {causa}" for r in sorted(alcance - ahora)]
            nuevos = [f for f in nuevos if str(f) in alcance]
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
            except CerrojoDeContenidoOcupado:
                raise                                           # otra operación tiene el catálogo ocupado: se detiene todo, no se reintenta archivo a archivo
            except FileNotFoundError:
                # desapareció entre la búsqueda y la lectura: no es un fallo de ZascArr, pero consta como omitido con su causa
                en_lote.omitted.append(f"{path.name} — desapareció antes de leerlo")
                en_lote.vanished += 1
            except ArchivoCambiado:
                en_lote.errors.append(f"{path.name}: cambió mientras se leía, así que no se ha registrado. Búscalo de nuevo")
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
                                     processed=report.processed, unreadable=report.unreadable)
        provisional.absorb(report)
        provisional.absorb(en_lote)
        run_id = await self._persist_run(provisional, kind="registro_incremental" if incremental else "adoption")
        # El marcador dice «el registro terminó». Con errores NO terminó: no se pone, y lo que
        # quedó sin registrar sigue a la vista (`inventario`) y se puede continuar repitiendo.
        # Tampoco con un recorrido parcial (#332): lo que no se pudo leer sigue sin registrar y el marcador cerraría la puerta a repetir.
        if not provisional.errors and not incremental and not report.unreadable:
            await RuntimeSettingsService(self._db).set_flag(_MARCADOR_HECHO, True)
        await self._confirmar_lote(en_lote, report, report.processed - confirmados, progreso, run_id)
        report.pending_count = 0
        return report

    # ── BL-R9: rescan de la biblioteca (a demanda y periódico) ─────────────

    async def rescanear(
        self, *, progreso: Callable[[RescanReport], None] | None = None,
        lote: int = _LOTE_POR_DEFECTO, disparador: str = "manual",
    ) -> RescanReport:
        """Reescanear la biblioteca: actualiza el catálogo por lo que hay AHORA en el disco.

        - **Nuevos** (ruta sin fila): se registran con `adopt(alcance=…)` — el mismo contrato de #326
          (identificado → serie; sin identificar → «Por revisar»; movidos → reenlace; copias → no se registran).
        - **Cambiados** (ruta con fila cuyo `stat` difiere de lo guardado, o línea de base sin fijar): se
          re-trían por contenido y la MISMA fila se actualiza (hash, tamaño, instante, vínculo) o se
          desvincula a «Por revisar». Nunca se crea una segunda fila ni se borra la existente.
        - **Iguales**: no se abren (solo el `stat`). **Desaparecidos**: `is_missing`/reaparición (B7).
        - Un recorrido incompleto (`unreadable > 0`) no impide procesar lo visible, pero el informe lo dice
          (`no_revisado`): nada se afirma como «sin cambios».

        Idempotente: repetirlo no duplica filas y un archivo que cambió mientras se leía se omite con causa
        (el siguiente rescan lo ve). El registro de los nuevos lo confirma `adopt` con su maquinaria de
        lotes y acreditación; los re-triajes se confirman por lotes de `lote` (una sola lectura de contenido
        por archivo, el `stat` del paseo es lo único que se paga por los que no cambiaron).
        """
        report = RescanReport(started_at=datetime.now(UTC), disparador=disparador)

        # Un solo paseo de rutas (sin leer contenido) en un hilo (CLAUDE.md §4).
        recorrido = await asyncio.to_thread(recorrer_comics, [self._library], COMIC_EXTS)
        files = recorrido.archivos
        report.files_scanned = len(files)
        report.unreadable = recorrido.ilegibles
        report.no_revisado = recorrido.ilegibles > 0

        filas = {f.file_path: f for f in (await self._db.execute(select(File))).scalars().all()}
        report.ya_registrados = sum(1 for f in files if str(f) in filas)

        def _partir() -> tuple[list[Path], list[tuple[Path, File]], int, int]:
            nuevos: list[Path] = []
            cambiados: list[tuple[Path, File]] = []
            sin_cambios = 0
            sin_consultar = 0
            for f in files:
                fila = filas.get(str(f))
                if fila is None:
                    nuevos.append(f)
                    continue
                try:
                    st = f.stat()
                except OSError:
                    # El recorrido sí lo `stat`ó; que falle ahora es un cambio a mitad de pasada.
                    # No se afirma ni «igual» ni «cambió»: el paseo queda incompleto (`no_revisado`).
                    sin_consultar += 1
                    continue
                if fila.file_mtime_ns is None or (st.st_size, st.st_mtime_ns) != (
                    fila.file_size_bytes, fila.file_mtime_ns
                ):
                    cambiados.append((f, fila))
                else:
                    sin_cambios += 1
            return nuevos, cambiados, sin_cambios, sin_consultar

        nuevos, cambiados, sin_cambios, sin_consultar = await asyncio.to_thread(_partir)
        report.sin_cambios = sin_cambios
        report.unreadable += sin_consultar
        report.no_revisado = report.no_revisado or sin_consultar > 0
        pistas = detectar_ordenes_de_lectura([f.name for f in files])

        # Lo nuevo, con el contrato completo del registro incremental (sin tocar su marcador).
        if nuevos:
            try:
                sub = await self.adopt(alcance=frozenset(str(f) for f in nuevos))
                report.nuevos_entregados = sub.processed
                report.nuevos_registrados = sub.registered_count - sub.relinked
                report.nuevos_a_revisar = sub.unsorted_count
                report.repetidos = sub.duplicate_count
                report.reenlazados = sub.relinked
                report.ambiguos += sub.ambiguous
                report.errores += sub.errors
                report.omitidos += sub.omitted
            except CerrojoDeContenidoOcupado:
                report.errores.append(
                    "El catálogo estaba ocupado por otra operación; los archivos nuevos no se han "
                    "registrado y se verán en el siguiente rescan")

        # Lo cambiado, archivo a archivo, en la MISMA fila.
        if cambiados:
            pendientes = 0

            def _marca_del_lote() -> tuple:
                """Foto de los contadores del informe: si el commit del lote no se acredita,
                sus re-triajes pasan a «por comprobar» y NO se cuentan dos veces (misma
                honestidad que los lotes de `adopt`: solo cuenta lo acreditado)."""
                return (report.re_triados, report.re_triados_igual, report.re_triados_cambiado,
                        report.re_triados_a_revisar, report.re_triados_descartado,
                        report.copias_de_otra, report.re_triados_protegidos,
                        report.discrepancias_registradas, len(report.errores), len(report.omitidos))

            def _deshacer_lote(marca: tuple) -> None:
                (report.re_triados, report.re_triados_igual, report.re_triados_cambiado,
                 report.re_triados_a_revisar, report.re_triados_descartado,
                 report.copias_de_otra, report.re_triados_protegidos,
                 report.discrepancias_registradas) = marca[:8]
                del report.errores[marca[8]:]
                del report.omitidos[marca[9]:]

            for _n, (path, fila) in enumerate(
                    sorted(cambiados, key=_clave_de_orden_de_retriaje), start=1):
                if pendientes == 0:
                    marca = _marca_del_lote()   # foto al EMPEZAR el lote: lo no acreditado se revierte a esto
                try:
                    async with self._db.begin_nested():
                        await self._re_triar_cambio(path, fila, report, pistas.get(path.name))
                    report.re_triados += 1
                    pendientes += 1
                except CerrojoDeContenidoOcupado:
                    report.errores.append(
                        "El catálogo estaba ocupado; el resto de archivos cambiados se verá en el siguiente rescan")
                    break
                except FileNotFoundError:
                    report.omitidos.append(f"{path.name} — desapareció antes de leerlo")
                except ArchivoCambiado:
                    report.omitidos.append(
                        f"{path.name} — cambió mientras se leía; se verá en el siguiente rescan")
                except Exception as exc:
                    logger.warning("library_adopter.retriaje_fallido", error=type(exc).__name__)
                    report.errores.append(
                        f"{path.name}: no se pudo re-clasificar ({type(exc).__name__})")
                if progreso is not None:
                    progreso(report)
                if pendientes >= lote:
                    if not await self._confirmar_lote_rescan(report, pendientes):
                        _deshacer_lote(marca)
                        pendientes = 0
                        break
                    pendientes = 0
            if pendientes == 0:
                marca = _marca_del_lote()
            if not await self._confirmar_lote_rescan(report, pendientes):
                _deshacer_lote(marca)

        # B7: disponibilidad de lo registrado (marca `is_missing`/revierte), con sus guardarraíles.
        try:
            comprobacion = await Importer(self._db)._comprobar_biblioteca()
            report.resultado_biblioteca = comprobacion.resultado.value
            report.desaparecidos = len(comprobacion.desaparecidos)
            report.reaparecidos = len(comprobacion.reaparecidos)
        except Exception:
            logger.exception("library_adopter.rescan_disponibilidad_fallida")
            report.resultado_biblioteca = "fallo_deteccion"
            report.errores.append(
                "No se pudo comprobar qué archivos siguen en su sitio; no se ha marcado ninguno "
                "como desaparecido")

        report.finished_at = datetime.now(UTC)
        try:
            report.run_id = await self._persist_run_rescan(report)
            await self._db.commit()
        except Exception:
            logger.exception("library_adopter.rescan_informe_fallido")
            with contextlib.suppress(Exception):
                await self._db.rollback()
            report.run_id = None
            report.errores.append("El rescan terminó pero su informe no se pudo guardar")
        return report

    async def _re_triar_cambio(
        self, path: Path, fila: File, report: RescanReport, pista: PistaDeCohorte | None = None
    ) -> None:
        """Un archivo registrado cuyo contenido cambió (o cuya línea de base no está fijada): se re-tría
        con el mismo pipeline que el registro (`_triage_and_match`) y se actualiza la MISMA fila.

        - Descartado a mano (`review_dismissed`): solo el stat, no se reactiva el descarte (#326 §4.1).
        - Ahora copia de otra fila presente: vínculo conservado (los bytes describen esa publicación).
        - Coincide con una fila desaparecida: esta fila sigue en su ruta; nada que reenlazar.
        - Identifica otra publicación: vínculo actualizado. No identifica: desvinculada → «Por revisar».
        """
        antes = await asyncio.to_thread(path.stat)
        outcome = await _triage_and_match(self._db, path, pista, excluir_fila=fila)
        if outcome.error_lectura:
            report.errores.append(f"{path.name}: no se pudo leer ({outcome.error_lectura})")
            return
        despues = await asyncio.to_thread(path.stat)
        if (antes.st_size, antes.st_mtime_ns) != (despues.st_size, despues.st_mtime_ns):
            raise ArchivoCambiado(path.name)
        tr = outcome.tr

        # F1 (#545): tagger, rescan, «Mantener lo mío» y la asignación manual comparten un
        # advisory lock por `File.id`. Hay que tomarlo ANTES de releer y mantenerlo hasta el
        # commit; si no, el rescan escribiría un `metadata_` leído antes de que «Mantener lo
        # mío» confirmara y se perdería `mantenida`/`discrepancias`.
        await bloquear_archivo(self._db, fila.id)
        fila = (await self._db.execute(
            select(File).where(File.id == fila.id).with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if fila is None:
            raise FileNotFoundError(str(path))

        if fila.review_dismissed:
            # Regla #326 §4.1: no se reactiva ningún descarte. Solo se actualiza la descripción de
            # los bytes (el stat debe describir el hash guardado, pase lo que pase con la clasificación).
            fila.file_size_bytes = antes.st_size
            fila.file_mtime_ns = antes.st_mtime_ns
            fila.sha256_hash = tr.sha256
            meta = dict(fila.metadata_ or {})
            if tr.formato_contenido:
                meta["formato_contenido"] = tr.formato_contenido
            meta.pop("comicinfo_estado", None)
            meta.pop("comicinfo_propio", None)
            fila.metadata_ = meta
            report.re_triados_descartado += 1
            return

        meta = dict(fila.metadata_ or {})
        if tr.formato_contenido:
            meta["formato_contenido"] = tr.formato_contenido

        if outcome.duplicate_of or outcome.recuperar is not None:
            # Los bytes nuevos ya constan en otra fila (presente o desaparecida): esta fila sigue en su
            # ruta y conserva su vínculo; solo se actualiza la descripción de los bytes.
            fila.file_size_bytes = antes.st_size
            fila.file_mtime_ns = antes.st_mtime_ns
            fila.sha256_hash = tr.sha256
            fila.is_missing = False
            fila.missing_since = None
            meta.pop("comicinfo_estado", None)
            meta.pop("comicinfo_propio", None)
            fila.metadata_ = meta
            if outcome.duplicate_of:
                report.copias_de_otra += 1
            report.re_triados_igual += 1
            return

        result = outcome.result
        is_unsorted = result.status == MatchStatus.UNSORTED or not result.series_id
        fila.file_size_bytes = antes.st_size
        fila.file_mtime_ns = antes.st_mtime_ns
        fila.sha256_hash = tr.sha256
        fila.is_missing = False
        fila.missing_since = None
        meta.update({
            "match_status": result.status,
            "match_score": result.score,
            "notes": result.notes,
            "candidates": serialize_candidates(result.candidates),
        })
        if outcome.cohorte_explicacion:
            meta["cohorte"] = outcome.cohorte_explicacion
        if outcome.edition_kind:
            meta["edicion"] = outcome.edition_kind
        # El contenido cambió: las marcas de ComicInfo describían los bytes anteriores.
        meta.pop("comicinfo_estado", None)
        meta.pop("comicinfo_propio", None)

        # D3-B4 (#233): ¿la relación ACTUAL es una aceptación humana? Si lo es, ninguna actualización
        # automática la cambia ni la vacía. Solo se actualizan los datos no relacionales y, si la
        # propuesta es otra publicación (o ninguna), se registra la discrepancia.
        issue_actual = None
        if fila.issue_id is not None:
            issue_actual = (await self._db.execute(
                select(Issue.series_id, Issue.issue_number, Issue.format)
                .where(Issue.id == fila.issue_id))).first()
        estado = estado_de_relacion(fila, issue_actual)
        if es_protegida(estado):
            relacion = relacion_actual(fila, issue_actual)
            meta = marcar_estado_por_relacion(meta, relacion)
            propuesta = await self._propuesta_del_cambio(tr, result, pista)
            anterior = str(fila.issue_id) if fila.issue_id else None
            nuevo = str(result.issue_id) if result.issue_id else None
            if anterior != nuevo and relacion is not None:
                meta, registrada = registrar(meta, crear_discrepancia(propuesta, relacion))
                report.re_triados_protegidos += 1
                if registrada:  # F4: repetir la misma observación no es una discrepancia nueva
                    report.discrepancias_registradas += 1
            elif anterior == nuevo:
                report.re_triados_igual += 1
            fila.metadata_ = meta
            return

        fila.metadata_ = meta
        if is_unsorted:
            if fila.issue_id is not None:
                fila.issue_id = None
                # La procedencia (`metadata_source`) se CONSERVA: describía la fila y el enricher
                # sabe restaurarla; borrarla perdería la pista sin ganar nada (decisión, spec §5).
            report.re_triados_a_revisar += 1
            return
        nuevo_vinculo = str(result.issue_id) if result.issue_id else None
        anterior = str(fila.issue_id) if fila.issue_id else None
        fila.issue_id = nuevo_vinculo
        # Un ComicInfo nuevo es evidencia fresca de procedencia; sin él se conserva la anterior.
        # `manual` no se pisa jamás (protección del enricher, CLAUDE.md).
        if tr.strong_candidate and fila.metadata_source != "manual":
            fila.metadata_source = "comicinfo_xml"
        if anterior == nuevo_vinculo:
            report.re_triados_igual += 1
        else:
            report.re_triados_cambiado += 1

    async def _propuesta_del_cambio(self, tr, resultado, pista: PistaDeCohorte | None) -> Propuesta:
        """La afirmación de la actualización, apta para la clave estable de D4: destino propuesto y
        discriminantes; sin ruta, nombre de archivo, score ni fecha."""
        destino = None
        if resultado.issue_id is not None:
            destino = (await self._db.execute(
                select(Issue.series_id, Issue.issue_number, Issue.format)
                .where(Issue.id == resultado.issue_id))).first()
        nombre = tr.path.name
        if pista is not None:
            nombre = quitar_prefijo_de_cohorte(nombre, pista)
        parsed = parse_comic_filename(nombre)
        return Propuesta(
            origen=ORIGEN_COMICINFO if tr.strong_candidate else ORIGEN_RESCAN,
            serie_destino_id=(str(destino.series_id) if destino is not None
                              else (str(resultado.series_id) if resultado.series_id else None)),
            issue_destino_uuid=str(resultado.issue_id) if resultado.issue_id else None,
            numero=destino.issue_number if destino is not None else (parsed.issue_number or None),
            formato=destino.format.value if destino is not None else (tr.file_format or parsed.format or None),
            titulo_norm=normalize_title(parsed.series) if parsed.series else None,
            anio=parsed.year,
        )

    async def _confirmar_lote_rescan(self, report: RescanReport, mirados: int) -> bool:
        """Commit del lote de re-triajes. Devuelve False si el commit falló: lo pendiente queda
        «por comprobar» y el bucle se detiene (la sesión puede estar rota). Nada se pierde: las
        actualizaciones son idempotentes y el siguiente rescan las rehace."""
        if mirados == 0:
            return True
        try:
            await self._db.commit()
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("library_adopter.rescan_commit_fallido", error=type(exc).__name__)
            with contextlib.suppress(Exception):
                await self._db.rollback()
            report.por_comprobar += mirados
            return False

    async def _persist_run_rescan(self, report: RescanReport) -> UUID:
        run = ImportRun(
            started_at=report.started_at,
            finished_at=report.finished_at,
            files_scanned=report.files_scanned,
            imported_count=report.nuevos_registrados + report.nuevos_a_revisar,
            duplicate_count=report.repetidos,
            unsorted_count=report.nuevos_a_revisar + report.re_triados_a_revisar,
            error_count=len(report.errores),
            disappeared_count=report.desaparecidos,
            details={
                "kind": "rescan",
                "disparador": report.disparador,
                "unreadable": report.unreadable,
                "no_revisado": report.no_revisado,
                "ya_registrados": report.ya_registrados,
                "sin_cambios": report.sin_cambios,
                "nuevos_entregados": report.nuevos_entregados,
                "nuevos_registrados": report.nuevos_registrados,
                "nuevos_a_revisar": report.nuevos_a_revisar,
                "repetidos": report.repetidos,
                "reenlazados": report.reenlazados,
                "re_triados": report.re_triados,
                "re_triados_igual": report.re_triados_igual,
                "re_triados_cambiado": report.re_triados_cambiado,
                "re_triados_a_revisar": report.re_triados_a_revisar,
                "re_triados_descartado": report.re_triados_descartado,
                "copias_de_otra": report.copias_de_otra,
                "re_triados_protegidos": report.re_triados_protegidos,
                "discrepancias_registradas": report.discrepancias_registradas,
                "desaparecidos": report.desaparecidos,
                "reaparecidos": report.reaparecidos,
                "resultado_biblioteca": report.resultado_biblioteca,
                "por_comprobar": report.por_comprobar,
                "ambiguos": report.ambiguos,
                "omitidos": report.omitidos,
                "errores": report.errores,
            },
        )
        self._db.add(run)
        await self._db.flush()
        return run.id

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
        # El hash se lee de los bytes que hay AHORA: si el archivo cambia mientras se lee, ese hash ya no lo describe y NO se registra (se
        # compara tamaño y fecha antes y después; un cambio que conserve ambos no se detecta, ver docs/design/registro-incremental-326.md).
        antes = await asyncio.to_thread(path.stat)
        outcome = await _triage_and_match(self._db, path, pista)
        if outcome.error_lectura:
            # Se pudo `stat` pero no leer: no se crea fila, no se mueve y no se pone el marcador
            # (es un error, no una omisión silenciosa). Se comprueba ANTES del segundo `stat`: si el
            # USB se cae y la ruta deja de estar, sigue siendo un error de lectura, no un «desapareció».
            report.errors.append(f"{path.name}: no se pudo leer ({outcome.error_lectura})")
            return
        despues = await asyncio.to_thread(path.stat)
        if (antes.st_size, antes.st_mtime_ns) != (despues.st_size, despues.st_mtime_ns):
            raise ArchivoCambiado(path.name)
        if outcome.recuperar is not None and self._incremental and outcome.n_recuperables > 1:
            # Varias filas desaparecidas tienen este mismo contenido: reenlazar la «más antigua» sería elegir por azar a cuál
            # pertenece. No se toca ninguna, no se crea una fila nueva y se informa.
            report.ambiguous.append(f"{path.name} — su contenido coincide con {outcome.n_recuperables} archivos que ya no están")
            return
        if (outcome.recuperar is not None and self._incremental
                and await asyncio.to_thread(_fichero_de_la_fila_existe, outcome.recuperar.file_path, path)):
            # Reenlazar mueve la ficha a esta ruta: solo si se puede afirmar que su ruta anterior YA no tiene el archivo. Si sigue ahí (la fila
            # quedó marcada como desaparecida por un fallo pasajero) o no se puede comprobar (otro disco, error al consultar), no se toca nada.
            report.ambiguous.append(
                f"{path.name} — su contenido coincide con un archivo registrado que ZascArr no ha podido dar por desaparecido")
            return
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
            report.relinked += 1
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
        if tr.formato_contenido:                                  # #307: formato REAL por contenido (file_format sigue siendo la extensión)
            metadata["formato_contenido"] = tr.formato_contenido

        # Nunca se mueve: file_path es la ruta real donde el coleccionista
        # ya tenía el archivo, no un destino calculado (a diferencia de
        # Importer._import_file).
        file_rec = File(
            issue_id=str(result.issue_id) if result.issue_id else None,
            file_path=str(path),
            file_name=path.name,
            file_format=FileFormat(path.suffix.lstrip(".").lower()),
            file_size_bytes=antes.st_size,
            # BL-R9: el stat guardado describe los bytes del hash guardado.
            file_mtime_ns=antes.st_mtime_ns,
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

    async def _persist_run(self, report: AdoptionReport, kind: str = "adoption") -> UUID:
        run = ImportRun(
            started_at=report.started_at,
            finished_at=report.finished_at,
            files_scanned=report.files_scanned,
            imported_count=report.registered_count,
            duplicate_count=report.duplicate_count,
            unsorted_count=report.unsorted_count,
            error_count=report.error_count,
            details={
                "kind": kind,
                "registered": report.registered,
                "duplicates": report.duplicates,
                "unsorted": report.unsorted,
                "errors": report.errors,
                "already_registered": report.already_registered,
                "by_other_run": report.by_other_run,
                "relinked": report.relinked,
                "ambiguous": report.ambiguous,
                "omitted": report.omitted,
                "unreadable": report.unreadable,
                # #332 residual 4: la aceptación no puede certificar un cierre con lotes sin acreditar.
                "reverted": report.reverted,
                "unknown": report.unknown,
            },
        )
        self._db.add(run)
        await self._db.flush()
        return run.id
