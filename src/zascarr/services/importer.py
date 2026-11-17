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
import errno
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import structlog
from sqlalchemy import cast, func, literal, or_, select, text, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.cohort import (
    PistaDeCohorte,
    detectar_ordenes_de_lectura,
    quitar_prefijo_de_cohorte,
)
from zascarr.core.formato_contenedor import formato_real_de
from zascarr.core.importer_triage import TriageResult, triage
from zascarr.core.matcher import MatchResult, MatchStatus, SeriesHit, SeriesMatcher
from zascarr.models import (
    EDITION_KIND_A_FORMAT,
    File,
    FileFormat,
    ImportRun,
    Issue,
    IssueFormat,
    ResultadoComprobacion,
    Series,
)
from zascarr.services import tareas
from zascarr.services.comicinfo import aplicar_a_issue
from zascarr.services.etiquetas_comicinfo import aplicar_comicinfo
from zascarr.services.raices import (
    FotoDeRaices,
    RaizNoDisponibleError,
    RaizResuelta,
    es_componente_de,
)
from zascarr.services.upgrades import reconciliar_mejora_importada
from zascarr.utils.espacio import EspacioInsuficienteError, comprobar_espacio
from zascarr.utils.fs import listar_comics, safe_move_en_raiz_async, sanitize_segment
from zascarr.utils.naming import parse_comic_filename
from zascarr.utils.nombres_biblioteca import construir_nombre, es_pack

logger = structlog.get_logger()

COMIC_EXTS = {".cbz", ".cbr", ".cb7", ".pdf", ".epub"}

# B7: umbral de "esto no son borrados a mano, esto es un disco desmontado"
# (ver _detectar_desaparecidos). Las dos condiciones aplican a la vez: por
# debajo de MINIMO archivos en biblioteca no merece la pena desconfiar
# (pocas filas en juego, bajo impacto de un falso positivo); por encima,
# más de la mitad desaparecida de golpe es mucho más probable un fallo de
# montaje que un vaciado real a mano.
UMBRAL_DESAPARICION_MASIVA_FRACCION = 0.5
UMBRAL_DESAPARICION_MASIVA_MINIMO = 10
# #307: filas por ciclo del relleno del formato real (cada una lee ≤ 512 B y, si es ZIP, su
# directorio central); ver contrato §12.2
LOTE_FORMATO_CONTENIDO = 100

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


# #231: errores de `stat` que significan «esa ruta no está». Cualquier otro (permiso, E/S, red) NO
# prueba ausencia: hace fallar la comprobación en vez de dar de baja. Es lo que hacía
# `Path.exists()` hasta Python 3.13; desde 3.14 se traga todos los errores y habría tratado un
# EACCES como «ausente»
# (el proyecto admite >=3.11, así que no se deja a la versión del intérprete).
_ERRNOS_DE_AUSENCIA = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP})


def _mensaje_sin_rutas(exc: BaseException, path: Path) -> str:
    """Mensaje para el informe sin la ruta absoluta del archivo/carpeta."""
    texto = str(exc)
    reemplazos = {
        str(path): path.name, str(path.resolve()): path.name,
        str(path.parent): "<carpeta>", str(path.parent.resolve()): "<carpeta>",
    }
    for absoluta, visible in reemplazos.items():
        if absoluta:
            texto = texto.replace(absoluta, visible)
    # Cualquier otra ruta absoluta que venga de una causa (p. ej. la raíz).
    return re.sub(r"(?<![\w.])/(?:[^\n\r\t]+?)(?=\s*(?:$|[.;:)]))", "<ruta>", texto)


def _existe(ruta: str) -> bool:
    try:
        os.stat(ruta)
    except OSError as exc:
        if exc.errno in _ERRNOS_DE_AUSENCIA:
            return False
        raise
    except ValueError:  # ruta con caracteres que el sistema no admite: no puede existir
        return False
    return True


# #231 (BL-R2): clave de `import_runs.details` con lo que observó la revisión de la biblioteca
# de ESE ciclo. Los ciclos anteriores no la traen y se leen como «sin dato».
CLAVE_COMPROBACION = "comprobacion_biblioteca"


@dataclass
class ComprobacionBiblioteca:
    """Lo que observó `_comprobar_biblioteca` en un ciclo: ámbito, resultado, recuentos y fecha.

    No decide nada por sí misma: `desaparecidos`/`reaparecidos` son las bajas y altas que el ciclo
    SÍ aplicó (vacías si un guardarraíl las omitió). Solo `como_dict()` se persiste (sin las listas,
    que ya viajan en `details["disappeared"]`/`["reappeared"]`)."""
    resultado: ResultadoComprobacion
    fecha: datetime
    ambito: str = "biblioteca"
    archivos_registrados: int | None = None  # None: no se pudo contar
    ausentes: int | None = None  # rutas registradas que no estaban (solo si se llegó a mirarlas)
    desaparecidos: list[str] = field(default_factory=list)
    reaparecidos: list[str] = field(default_factory=list)
    #: Estado observado POR RAÍZ (#156, corte C). Compatible: una instalación de una raíz
    #: deja una sola entrada. Cada entrada: id, nombre, resultado, archivos, ausentes.
    raices: list[dict] = field(default_factory=list)

    @property
    def bajas_omitidas(self) -> bool:
        """Si el ciclo NO miró (o no se fió de) las rutas: no se marcó ninguna baja ni alta."""
        return self.resultado is not ResultadoComprobacion.COMPROBADA

    def como_dict(self) -> dict:
        return {
            "ambito": self.ambito,
            "resultado": self.resultado.value,
            "archivos_registrados": self.archivos_registrados,
            "ausentes": self.ausentes,
            "bajas_omitidas": self.bajas_omitidas,
            "fecha": self.fecha.isoformat(),
            "raices": self.raices,
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
    # #231: resultado de esa revisión; None solo si el ciclo ni llegó a ella
    comprobacion: ComprobacionBiblioteca | None = None
    # #232: id del ImportRun persistido y origen de la ejecución (manual/automatico).
    run_id: UUID | None = None
    disparador: str = "automatico"

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
    #: causa si el fichero se pudo `stat` pero no leer: no hay match ni duplicado
    #: posible. Lo informa el consumidor; nunca se crea fila ni se mueve nada.
    error_lectura: str | None = None
    result: MatchResult | None = None  # None si es un duplicado o una recuperación
    duplicate_of: str | None = None
    # Integridad (benchmark-integridad-hash-dedupe): cuando TODAS las
    # coincidencias por hash están `is_missing`, el fichero que vuelve a llegar
    # es el mismo contenido que una fila desaparecida — se reenlaza esa fila en
    # vez de crear otra o descartar. Lleva la fila a reenlazar.
    recuperar: File | None = None
    #: cuántas filas desaparecidas tenían ese contenido (si > 1, `recuperar` es arbitraria)
    n_recuperables: int = 0
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


def _dispositivo(ruta: str | Path) -> int:
    return os.stat(ruta).st_dev


def _fichero_de_la_fila_existe(ruta_fila: str, nuevo: Path) -> bool:
    """¿El archivo que una fila `is_missing = false` dice tener está de verdad donde dice?

    Una fila puede quedar apuntando a una ruta que ya no existe sin que nadie la haya marcado como
    desaparecida (p. ej. un archivo movido con la BD sin actualizar, o una carpeta reorganizada a
    mano). Tratarla como «copia presente» descartaba como repetido el archivo real y dejaba la fila
    apuntando a la nada.

    Devuelve False SOLO cuando se puede afirmar que no existe: el archivo falta y el primer
    ancestro que sí existe está en el MISMO sistema de ficheros que `nuevo` (el archivo que acaba
    de leerse). Si el sitio viejo cuelga de otro disco, puede estar desmontado y NO se afirma que
    falte; ante cualquier duda (error al consultar, ningún ancestro visible) se devuelve True: es
    el comportamiento de siempre, el conservador."""
    antiguo = Path(ruta_fila)
    try:
        os.stat(antiguo)
        return True
    except FileNotFoundError:
        pass
    except OSError:
        return True        # permisos, E/S…: no se sabe → comportamiento de siempre
    for ancestro in antiguo.parents:
        try:
            os.stat(ancestro)
        except FileNotFoundError:
            continue
        except OSError:
            return True
        try:
            return _dispositivo(ancestro) != _dispositivo(nuevo)
        except OSError:
            return True
    return True


#: #326: cerrojo de transacción de Postgres que serializa «buscar por contenido -> insertar» entre
#: TODOS los que crean filas por contenido (el importador y el registro de la biblioteca). Una sola
#: clave: una transacción larga (el ciclo del importador) ocupa UNA entrada de la tabla de cerrojos.
_CERROJO_CONTENIDO = (326, 1)
#: Cuánto espera un escritor a que otro termine su transacción antes de rendirse.
ESPERA_MAXIMA_CERROJO_CONTENIDO_S = 60.0
_PAUSA_CERROJO_S = 0.25


class CerrojoDeContenidoOcupado(Exception):  # noqa: N818  (nombre de dominio, como el resto)
    """Otra operación (importador o registro) lleva demasiado con el cerrojo."""


async def tomar_cerrojo_de_contenido(db: AsyncSession) -> None:
    """Espera (con tope) a ser el ÚNICO que busca por contenido e inserta; lo conserva hasta el
    fin de SU transacción.

    Sin esto, el importador y el registro podían leer «no hay nadie con este contenido» a la vez e
    insertar cada uno su fila (la columna no es única). Con él, el segundo, al entrar, ya ve lo que
    el primero CONFIRMÓ y lo trata como repetido. Solo actúa con una sesión real de Postgres; con
    dobles de prueba no hace nada. Es re-entrante dentro de una transacción. Si no se obtiene a
    tiempo lanza `CerrojoDeContenidoOcupado`: quien llama no debe insertar."""
    if not isinstance(db, AsyncSession):
        return
    limite = time.monotonic() + ESPERA_MAXIMA_CERROJO_CONTENIDO_S
    clase, objeto = _CERROJO_CONTENIDO
    while True:
        obtenido = (await db.execute(
            text("SELECT pg_try_advisory_xact_lock(:c, :o)"), {"c": clase, "o": objeto})).scalar()
        if obtenido:
            return
        if time.monotonic() >= limite:
            raise CerrojoDeContenidoOcupado
        await asyncio.sleep(_PAUSA_CERROJO_S)


async def _coincidencias_de_hash(db: AsyncSession, sha256: str) -> list[File]:
    """Filas cuyo contenido coincide con `sha256`, por `sha256_hash` **o**
    `original_sha256` (integridad). Orden determinista: las presentes
    (`is_missing = false`) primero, luego por `imported_at` — así la primera
    decide el caso: si está presente es un duplicado real, si está desaparecida
    es que TODAS lo están (y hay que reenlazar)."""
    return list((await db.execute(
        select(File)
        .where(or_(File.sha256_hash == sha256, File.original_sha256 == sha256))
        .order_by(File.is_missing.asc(), File.imported_at.asc())
    )).scalars().all())


async def _reenlazar_fila(fila: File, tr: TriageResult, dest: Path, *,
                          root_id: UUID | None = None) -> None:
    """Actualiza la fila `is_missing` para que describa el fichero que YA está
    en `dest` (quien llama decide si lo movió —Importer— o ya estaba ahí
    —LibraryAdopter—).

    Conserva el enlace a Issue/Series y `original_sha256`; reinicia `imported_at`
    (D8 cierra por `File.imported_at >= Wishlist.added_at`, y reactivar un
    `IMPORTED` reinicia `added_at`) y, si el fichero es el ORIGINAL de una fila
    etiquetada, vacía `comicinfo_estado`/`comicinfo_propio` (describen un
    fichero que ya no existe).

    El `file_format` (la extensión DECLARADA) sigue a `dest`: un fichero que
    vuelve con otra extensión no puede seguir anunciando la vieja. El formato
    REAL por contenido va aparte, en `metadata_["formato_contenido"]`."""
    fila.file_path = str(dest)
    if root_id is not None:
        fila.root_id = root_id
    fila.file_name = dest.name
    fila.file_format = FileFormat(dest.suffix.lstrip(".").lower())
    stat_dest = dest.stat()
    fila.file_size_bytes = stat_dest.st_size
    # BL-R9: el stat guardado describe los bytes del hash guardado.
    fila.file_mtime_ns = stat_dest.st_mtime_ns
    fila.sha256_hash = tr.sha256
    fila.is_missing = False
    fila.missing_since = None
    fila.imported_at = datetime.now(UTC)
    meta = dict(fila.metadata_ or {})
    # #307: el formato REAL del fichero que ahora está en `dest`
    if tr.formato_contenido:
        meta["formato_contenido"] = tr.formato_contenido
    if fila.original_sha256 is not None and tr.sha256 == fila.original_sha256:
        meta.pop("comicinfo_estado", None)
        meta.pop("comicinfo_propio", None)
    fila.metadata_ = meta


@dataclass(frozen=True)
class ResultadoRelleno:
    """Resultado identificable de una ejecución del relleno de `formato_contenido`."""
    limite: int
    pendientes_antes: int
    leidas: int
    rellenadas: int
    ilegibles: int           # no se marcan: siguen pendientes y se reintentan
    pendientes_despues: int


def _sin_formato_contenido():
    """`metadata` sin la clave. Ojo: con `metadata` NULL, `NOT (metadata ? 'clave')` vale NULL (no
    verdadero) y la fila no se elegiría nunca."""
    return or_(File.metadata_.is_(None), ~File.metadata_.has_key("formato_contenido"))


async def _triage_sin_bloquear(path: Path) -> TriageResult:
    """`triage` lee el fichero ENTERO para hashearlo: es lo más caro de adoptar
    o importar y se hace una vez por fichero. Sobre una biblioteca en red, hacerlo
    en el bucle de eventos congelaba la app (ensayo con 160 GB en SMB, 2026-10-01);
    en un hilo, la interfaz sigue respondiendo (CLAUDE.md §4)."""
    return await asyncio.to_thread(triage, path)


async def _triage_and_match(
    db: AsyncSession, path: Path, pista: PistaDeCohorte | None = None,
    excluir_fila: File | None = None,
) -> _Outcome:
    tr: TriageResult = await _triage_sin_bloquear(path)

    if tr.error_lectura:
        # Sin lectura no hay hash ni match: ni duplicado, ni reenlace, ni fila. Se corta aquí,
        # antes de deduplicar o buscar serie, y cada consumidor lo informa como error.
        return _Outcome(tr=tr, error_lectura=tr.error_lectura)

    if tr.sha256:
        # #326: hasta el fin de la transacción nadie más busca-e-inserta por contenido
        await tomar_cerrojo_de_contenido(db)
        coincidencias = await _coincidencias_de_hash(db, tr.sha256)
        # BL-R9 (re-triaje de una ruta registrada): la fila que se está actualizando NO cuenta
        # como coincidencia — su hash describe el contenido ANTERIOR. Sin la exclusión, un archivo
        # cuyo contenido no cambió (solo su stat) se leería como «duplicado de sí mismo».
        if excluir_fila is not None:
            coincidencias = [c for c in coincidencias if c.id != excluir_fila.id]
        if coincidencias:
            if len(coincidencias) > 1:
                # Integridad: la columna no es única; dos filas con el mismo
                # hash deben poder representarse, pero es raro y conviene que
                # quede rastro (antes esto reventaba con MultipleResultsFound).
                logger.warning(
                    "importer.dedupe_coincidencias_multiples",
                    hash=tr.sha256[:12], filas=len(coincidencias),
                )
            # Una copia cuenta como presente solo si su fichero EXISTE de verdad. Una fila
            # `is_missing = false` cuya ruta ya no existe (referencia obsoleta) no es un duplicado:
            # es la fila a recuperar.
            for fila in coincidencias:
                if fila.is_missing:
                    continue
                if await asyncio.to_thread(_fichero_de_la_fila_existe, fila.file_path, tr.path):
                    return _Outcome(tr=tr, result=None, duplicate_of=fila.file_name)
                logger.info("importer.referencia_obsoleta", fila=str(fila.id))  # sin ruta (§5.4)
            # Ninguna coincidencia tiene su fichero (desaparecidas o con la ruta obsoleta):
            # recuperar la más antigua en vez de descartar o crear una fila nueva.
            return _Outcome(
                tr=tr, result=None, recuperar=coincidencias[0], n_recuperables=len(coincidencias))

    matcher = SeriesMatcher(db)

    # El nombre se limpia de la pista de cohorte y se parsea UNA vez, antes de
    # decide(): de ahí salen tanto (serie, número, año) como el marcador de
    # edición. B15 necesita ese marcador ANTES de decidir — el matcher no debe
    # enlazar un Tomo/Omnigold a una grapa que ocupe el mismo número. Antes se
    # parseaba dentro del extractor y edition_kind solo se conocía al terminar
    # decide(), demasiado tarde para influir en la decisión.
    aplicada = False
    nombre = tr.path.name
    if pista is not None:
        nombre = quitar_prefijo_de_cohorte(tr.path.name, pista)
        aplicada = nombre != tr.path.name
    carpetas = [tr.path.parent.parent.name, tr.path.parent.name]
    contexto = " / ".join(c for c in carpetas if c and c not in (".", ".."))
    parsed = parse_comic_filename(nombre, carpeta=tr.path.parent.name, contexto=contexto)
    edition_kind = parsed.edition_kind
    # B15: `None` significa "el nombre NO trae marcador de edición" — el matcher
    # entonces no tiene evidencia del formato y solo enlazará si no hay nada que
    # desambiguar (una única candidata). Un marcador explícito (Omnigold/Tomo…)
    # sí es evidencia y permite elegir entre varias ediciones del mismo número.
    formato_esperado = (
        EDITION_KIND_A_FORMAT.get(edition_kind, IssueFormat.SINGLE_ISSUE).value
        if edition_kind is not None
        else None
    )

    def extractor(filename: str):
        if parsed.series and parsed.issue_number:
            return parsed.series, parsed.issue_number, parsed.year
        return None

    # Un anual solo puede enlazar con una serie anual: `parsed.series` conserva
    # «Annual» y `annual=True` impide que el matcher acepte la serie madre.
    kwargs = {}
    if parsed.series_alternativa:
        kwargs["series_alternativa"] = parsed.series_alternativa
    result = await matcher.decide(
        tr, extractor=extractor, formato_esperado=formato_esperado,
        annual=parsed.is_annual, **kwargs,
    )
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
    def __init__(self, db: AsyncSession, *, foto_raices: FotoDeRaices | None = None):
        self._db = db
        self._foto_inyectada = foto_raices
        self._foto_raices = foto_raices
        s = get_settings()
        self._library = s.library_path
        self._scan_dirs = [
            Path(s.transmission_download_dir),
            Path(s.amule_incoming_dir),
            s.downloads_path,
        ]

    async def scan_and_import(self, *, disparador: str = "automatico") -> ImportReport:
        try:
            # Foto nueva por ciclo: un cambio de mapeo a mitad no cambia el destino de este ciclo.
            self._foto_raices = getattr(self, "_foto_inyectada", None)
            report = ImportReport(started_at=datetime.now(UTC), disparador=disparador)

            # Dedupe por (st_dev, st_ino), no por ruta: ver `listar_comics`. El
            # recorrido va en un hilo — bloquea en E/S (CLAUDE.md §4).
            tarea = tareas.iniciar("importar", enlace="/ui/no-disponibles#comprobar-disco",
                                   origen=f"importar:{disparador}")
            files = await asyncio.to_thread(listar_comics, self._scan_dirs, COMIC_EXTS)
            report.files_scanned = len(files)
            if tarea is not None:
                tareas.actualizar(tarea.id, total=len(files), fase="Importando")

            # Evidencia de cohorte (core/cohort.py): calculada UNA VEZ sobre la
            # foto fija de este ciclo, antes del bucle — contrato de
            # determinismo (2026-09-26): un archivo que llega a mitad de ciclo
            # no puede cambiar la cohorte ya calculada para los anteriores.
            pistas = detectar_ordenes_de_lectura([f.name for f in files])

            for indice, path in enumerate(sorted(files), 1):
                if tarea is not None:
                    tareas.actualizar(tarea.id, hechos=indice)
                try:
                    await self._import_file(path, report, pistas.get(path.name))
                except CerrojoDeContenidoOcupado:
                    # Otra operación (p. ej. un registro de la biblioteca) lleva mucho
                    # con el cerrojo: el archivo se queda donde está y se reintenta.
                    logger.warning("importer.cerrojo_de_contenido_ocupado")
                    report.errors.append(
                        f"{path.name}: otra operación estaba registrando contenido; "
                        "se reintentará en el próximo ciclo")
                    # Los demás esperarían lo mismo (60 s cada uno): se corta el
                    # recorrido. Siguen en descargas y el próximo ciclo los retoma.
                    report.errors.append(
                        "El ciclo se detuvo antes de mirar el resto de las descargas")
                    break
                except Exception as exc:
                    try:
                        inodo = path.stat(follow_symlinks=False).st_ino
                    except OSError:
                        inodo = None
                    logger.error(
                        "importer.file_failed", inodo=inodo,
                        formato=path.suffix.lstrip(".") or "sin_extension",
                        error_tipo=type(exc).__name__)
                    report.errors.append(f"{path.name}: {_mensaje_sin_rutas(exc, path)}")

            # B7: revisión de la biblioteca YA importada, no de lo nuevo que
            # acaba de llegar — un paso independiente del bucle de arriba.
            try:
                comprobacion = await self._comprobar_biblioteca()
            except Exception as exc:
                # Un fallo no marca ninguna baja, pero tampoco puede pasar por «no pasó nada»: queda
                # escrito en el informe (#231, criterio 11), sin afirmar causa.
                logger.error("importer.deteccion_desaparecidos_fallida",
                             error=type(exc).__name__)
                comprobacion = ComprobacionBiblioteca(
                    resultado=ResultadoComprobacion.FALLO_DETECCION, fecha=datetime.now(UTC))
            report.comprobacion = comprobacion
            report.disappeared = comprobacion.desaparecidos
            report.reappeared = comprobacion.reaparecidos

            report.finished_at = datetime.now(UTC)
            if tarea is not None:
                tareas.terminar(tarea.id, resumen="Descargas revisadas")
            await self._persist_run(report)
            return report

        except BaseException as exc:
            if tarea is not None:
                tareas.error(tarea.id, tipo_error=type(exc).__name__)
            raise
        finally:
            if tarea is not None and tarea.estado.value == "en_curso":
                tareas.terminar(tarea.id, resumen="Descargas revisadas")

    async def rellenar_formato_contenido(
        self, limite: int = LOTE_FORMATO_CONTENIDO
    ) -> ResultadoRelleno:
        """#307 (D5, decidida a demanda): guarda en `files.metadata["formato_contenido"]` el
        formato REAL de los `.cbr`/`.cb7` ya registrados que aún no
        lo tienen (solo lectura del fichero: ≤ 512 bytes y, si es un ZIP, su directorio central).
        Sin migración.

        **NO se ejecuta sola**: ni `scan_and_import` ni ningún bucle la llaman. Se pide
        explícitamente (`python -m zascarr.cli.rellenar_formato --apply`,
        o `scripts/rellenar-formato.sh`) y devuelve un resultado identificable. Automatizarla
        exigiría antes medir su coste de lectura en el USB y aprobar su presupuesto.

        Garantías (pruebas con Postgres real en `tests/test_formato_contenido_relleno_pg.py`):
          · **Conserva las demás claves** de `metadata` aunque otro proceso las escriba entre la
          lectura y la escritura: no se reescribe el diccionario
            entero, se FUSIONA en la base (`metadata || {...}`) en una sola sentencia atómica por
            fila.
          · **No sobrescribe**: la sentencia solo actúa si la clave aún no existe (`metadata IS
          NULL OR NOT metadata ? 'formato_contenido'`), así que dos
            ejecuciones solapadas no se pisan y una fila rellena no se lee otra vez.
          · **Acotado**: como máximo `limite` filas por ejecución, ELEGIDAS AL AZAR entre las
          pendientes (si fueran siempre las mismas, un grupo de ficheros
            ilegibles ocuparía el lote para siempre; el azar reduce ese riesgo pero NO garantiza
            un plazo de finalización).
          · Un fichero ilegible (disco desmontado, permisos) no se marca: queda pendiente y se
          reintenta, no se clasifica como «sin contenido»."""
        pendientes_antes = await self.contar_pendientes_formato()
        candidatas = await self._candidatas_formato(limite)
        if not candidatas:
            return ResultadoRelleno(limite=limite, pendientes_antes=pendientes_antes,
                                    leidas=0, rellenadas=0, ilegibles=0,
                                    pendientes_despues=pendientes_antes)
        formatos = await asyncio.to_thread(
            lambda: [formato_real_de(Path(ruta)) for _id, ruta in candidatas])
        rellenadas = await self._aplicar_formato(candidatas, formatos)
        ilegibles = sum(1 for fc in formatos if fc is None)
        pendientes_despues = await self.contar_pendientes_formato()
        logger.info("importer.formato_contenido_rellenado", filas=rellenadas,
                    leidas=len(candidatas), ilegibles=ilegibles,
                    pendientes=pendientes_despues)
        return ResultadoRelleno(limite=limite, pendientes_antes=pendientes_antes,
                                leidas=len(candidatas), rellenadas=rellenadas,
                                ilegibles=ilegibles, pendientes_despues=pendientes_despues)

    async def contar_pendientes_formato(self) -> int:
        """Cuántas filas `.cbr`/`.cb7` presentes aún no tienen `formato_contenido` (no lee ningún
        fichero)."""
        return (await self._db.execute(
            select(func.count(File.id)).where(
                File.file_format.in_([FileFormat.CBR, FileFormat.CB7]),
                File.is_missing.is_(False), _sin_formato_contenido())
        )).scalar_one()

    async def _candidatas_formato(self, limite: int) -> list[tuple]:
        filas = (await self._db.execute(
            select(File.id, File.file_path)
            .where(File.file_format.in_([FileFormat.CBR, FileFormat.CB7]),
                   File.is_missing.is_(False), _sin_formato_contenido())
            .order_by(func.random()).limit(limite)
        )).all()
        return [(f.id, f.file_path) for f in filas]

    async def _aplicar_formato(self, candidatas: list[tuple], formatos: list[dict | None]) -> int:
        rellenadas = 0
        for (fid, _ruta), fc in zip(candidatas, formatos, strict=True):
            if fc is None:
                continue
            nuevo = func.coalesce(File.metadata_, cast(literal("{}"), JSONB)).op("||")(
                cast(literal(json.dumps({"formato_contenido": fc})), JSONB))
            res = await self._db.execute(
                update(File).where(File.id == fid, _sin_formato_contenido())
                .values(metadata_=nuevo).execution_options(synchronize_session=False))
            rellenadas += res.rowcount or 0
        return rellenadas

    async def _detectar_desaparecidos(self) -> tuple[list[str], list[str]]:
        """B7: un tebeo borrado a mano del disco (fuera de ZascArr) deja
        de contar como "lo tienes" sin que nadie tenga que avisar.

        Guardarraíles (endurecidos tras revisión de PR, 2026-09-26): dos
        formas de confundir "disco desmontado" con "he perdido toda mi
        colección", ninguna cubierta por el simple exists()/is_dir() de
        más abajo.

        1. **Punto de montaje vacío pero accesible**: un disco de red o
           USB desmontado a menudo deja atrás el propio directorio de
           montaje — sigue existiendo, sigue siendo un directorio, pero
           está vacío. `exists()/is_dir()` no lo distingue de una
           biblioteca real; comprobar que tiene contenido, sí.
        2. **Desaparición masiva anómala**: aun con la carpeta accesible
           y no vacía, un fallo de montaje parcial (p.ej. NFS que
           resuelve el directorio pero no su contenido) puede hacer que
           la mayoría de rutas den `exists() == False` de golpe. Eso es
           mucho más probable un problema de infraestructura que "el
           coleccionista borró medio armario a mano" — se aborta sin
           tocar nada y se avisa, en vez de convertir esto en cientos de
           cambios de estado silenciosos.
        """
        comprobacion = await self._comprobar_biblioteca()
        return comprobacion.desaparecidos, comprobacion.reaparecidos

    async def _comprobar_biblioteca(self) -> ComprobacionBiblioteca:
        """Revisa la disponibilidad POR RAÍZ (#156, corte C).

        Una raíz caída, vacía o con desaparición masiva se omite ENTERA y no marca bajas de
        sus archivos ni contamina a las demás. Los `File.root_id NULL` no se atribuyen a
        ninguna raíz ni se marcan por la caída de otra. En una instalación de una sola raíz
        el resultado y los recuentos son los mismos que antes.
        """
        fecha = datetime.now(UTC)
        foto = await self._foto()
        todas = list((await self._db.execute(select(File))).scalars().all())
        estados: list[dict] = []
        desaparecidos: list[str] = []
        reaparecidos: list[str] = []
        ausentes_total: int | None = 0
        vistos: set[object] = set()

        raices = [r for r in foto.raices if bool(getattr(r, "enabled", True))]
        for raiz in raices:
            def de_esta_raiz(f: File, raiz=raiz) -> bool:
                if getattr(raiz, "id", None) is None:
                    # Compatibilidad con dobles de una sola raíz sin tabla.
                    return f.root_id is None and es_componente_de(f.file_path, raiz.path)
                # `root_id NULL` bajo la raíz es una fila heredada aún sin backfill: se
                # cuenta en su raíz por componentes, nunca en otra.
                return (f.root_id is not None and str(f.root_id) == str(raiz.id)) or (
                    f.root_id is None and es_componente_de(f.file_path, raiz.path))

            archivos = [f for f in todas if de_esta_raiz(f)]
            vistos.update(id(f) for f in archivos)
            ruta = Path(raiz.path)
            info = {"id": str(raiz.id) if getattr(raiz, "id", None) is not None else None,
                    "nombre": str(raiz.name), "resultado": "", "archivos": len(archivos),
                    "ausentes": None}
            if not await asyncio.to_thread(ruta.is_dir):
                logger.warning("importer.raiz_inaccesible_omitiendo_desaparecidos", raiz=raiz.name)
                info["resultado"] = ResultadoComprobacion.RAIZ_INACCESIBLE.value
                ausentes_total = None
                estados.append(info)
                continue
            if not archivos:
                info["resultado"] = ResultadoComprobacion.COMPROBADA.value
                info["ausentes"] = 0
                estados.append(info)
                continue
            vacia = await asyncio.to_thread(lambda ruta=ruta: not any(ruta.iterdir()))
            if vacia:
                logger.warning("importer.raiz_vacia_omitiendo_desaparecidos", raiz=raiz.name)
                info["resultado"] = ResultadoComprobacion.RAIZ_VACIA.value
                estados.append(info)
                continue
            rutas = [f.file_path for f in archivos]
            ausentes = await asyncio.to_thread(
                lambda rutas=rutas: {r for r in rutas if not _existe(r)})
            ausentes_total += len(ausentes)
            if (
                len(archivos) >= UMBRAL_DESAPARICION_MASIVA_MINIMO
                and len(ausentes) > len(archivos) * UMBRAL_DESAPARICION_MASIVA_FRACCION
            ):
                logger.error("importer.desaparicion_masiva_anomala_abortando",
                             ausentes=len(ausentes), total_files=len(archivos), raiz=raiz.name)
                info["resultado"] = ResultadoComprobacion.DESAPARICION_MASIVA.value
                info["ausentes"] = len(ausentes)
                estados.append(info)
                continue
            for f in archivos:
                ausente = f.file_path in ausentes
                if ausente and not f.is_missing:
                    f.is_missing = True
                    f.missing_since = datetime.now(UTC)
                    desaparecidos.append(f.file_name)
                elif not ausente and f.is_missing:
                    f.is_missing = False
                    f.missing_since = None
                    reaparecidos.append(f.file_name)
            info["resultado"] = ResultadoComprobacion.COMPROBADA.value
            info["ausentes"] = len(ausentes)
            estados.append(info)

        # Los archivos fuera de toda raíz no se atribuyen ni se dan de baja por una raíz caída.
        fuera_de_raiz = sum(1 for f in todas if id(f) not in vistos)
        if fuera_de_raiz:
            estados.append({"id": None, "nombre": "Fuera de raíz", "resultado": "fuera_de_raiz",
                            "archivos": fuera_de_raiz, "ausentes": None})

        resultados = [e["resultado"] for e in estados]
        if not raices or ResultadoComprobacion.RAIZ_INACCESIBLE.value in resultados:
            resultado = ResultadoComprobacion.RAIZ_INACCESIBLE
        elif ResultadoComprobacion.RAIZ_VACIA.value in resultados:
            resultado = ResultadoComprobacion.RAIZ_VACIA
        elif ResultadoComprobacion.DESAPARICION_MASIVA.value in resultados:
            resultado = ResultadoComprobacion.DESAPARICION_MASIVA
        else:
            resultado = ResultadoComprobacion.COMPROBADA

        if desaparecidos or reaparecidos:
            await self._db.flush()
        return ComprobacionBiblioteca(
            resultado=resultado, fecha=fecha, archivos_registrados=len(todas),
            ausentes=ausentes_total, desaparecidos=desaparecidos,
            reaparecidos=reaparecidos, raices=estados)

    async def _foto(self) -> FotoDeRaices:
        """Foto de raíces por ciclo: una consulta, aunque haya muchos archivos."""
        foto = getattr(self, "_foto_raices", None)
        if foto is None:
            if isinstance(self._db, AsyncSession):
                foto = await FotoDeRaices.cargar(self._db)
                biblioteca = getattr(self, "_library", None)
                if foto.raices and biblioteca is not None and not any(
                        str(biblioteca) == str(r.path) for r in foto.raices):
                    # Configuración de una sola raíz antigua (o doble de prueba): la raíz de
                    # settings sigue siendo la que se recorre. En producción las filas mandan.
                    foto = FotoDeRaices.compatibilidad(path=biblioteca)
            else:
                # Dobles de prueba sin tabla de raíces: reproducción de una instalación de una raíz.
                foto = FotoDeRaices.compatibilidad(
                    path=getattr(self, "_library", None))
            self._foto_raices = foto
        return foto

    async def _raiz(
        self, tradicion, *, por_defecto: bool = False
    ) -> tuple[FotoDeRaices, RaizResuelta]:
        foto = await self._foto()
        raiz = foto.por_defecto() if por_defecto else foto.por_tradicion(tradicion)
        # H3: la foto conserva el mapeo, pero se revalida la raíz en cada movimiento.
        if raiz.id is not None:
            raiz = foto.raiz_para_escritura(raiz.id)
        return foto, raiz

    async def _import_file(
        self, path: Path, report: ImportReport, pista: PistaDeCohorte | None = None
    ) -> None:
        outcome = await _triage_and_match(self._db, path, pista)
        if outcome.error_lectura:
            # Se pudo `stat` pero no leer: no se mueve, no se crea fila y se informa con la causa.
            report.errors.append(f"{path.name}: no se pudo leer ({outcome.error_lectura})")
            return
        if outcome.recuperar is not None:
            await self._reenlazar(outcome.recuperar, path, outcome.tr, report)
            return
        if outcome.duplicate_of:
            report.duplicates.append(
                f"{path.name} — duplicado de {outcome.duplicate_of}, descartado"
            )
            logger.debug(
                "importer.duplicate",
                inodo=path.stat(follow_symlinks=False).st_ino,
                formato=path.suffix.lstrip(".") or "sin_extension",
            )
            return
        tr, result = outcome.tr, outcome.result
        is_unsorted = result.status == MatchStatus.UNSORTED or not result.series_id
        ajustes = get_settings()

        # Resolver la raíz ANTES de construir la ruta o mover: si no está
        # disponible, el archivo se queda en la cola y no se inventa otra.
        series_obj = None
        if not is_unsorted:
            series_obj = (await self._db.execute(
                select(Series).where(Series.id == result.series_id)
            )).scalar_one_or_none()
            if series_obj is None:
                is_unsorted = True
        parsed_para_destino = parse_comic_filename(path.name, carpeta=path.parent.name)
        numero_destino: str | None = (
            (tr.comic_info.number if tr.strong_candidate and tr.comic_info else None)
            or parsed_para_destino.issue_number
        )
        crear_numero = bool(getattr(ajustes, "import_create_missing_issue", False))
        if not crear_numero and result.issue_id is None:
            # Sin la opción B23 se conserva el nombre original: es el contrato
            # histórico de los archivos que no tienen número enlazado.
            numero_destino = None
        # El número se crea DESPUÉS de mover: si falla la raíz o el espacio,
        # no puede quedar un Issue huérfano. Si ya hay catálogo, el archivo no
        # inventa el número: va a Pendientes como discrepancia. Un especial,
        # un pack o un nombre poco fiable tampoco identifican UNA grapa.
        puede_crear_numero = bool(
            numero_destino
            and parsed_para_destino.edition_kind is None
            and not parsed_para_destino.is_special
            and not parsed_para_destino.is_pack
            and (tr.strong_candidate or parsed_para_destino.confidence >= 0.7)
        )
        if (not is_unsorted and result.issue_id is None and crear_numero
                and (not puede_crear_numero
                     or await self._serie_tiene_numeros(result.series_id))):
            is_unsorted = True
            result.status = MatchStatus.UNSORTED
            result.notes.append(
                "número no enlazado en una serie ya catalogada: se deja para revisar")
        elif (not is_unsorted and result.issue_id is None and not crear_numero
                and result.notes):
            # Comportamiento histórico seguro: un match de serie sin número
            # registrado no se presenta como importado. Los dobles de prueba
            # sin notas conservan su contrato de raíz.
            is_unsorted = True
            result.status = MatchStatus.UNSORTED
        try:
            foto, raiz = await self._raiz(
                getattr(series_obj, "tradition", None), por_defecto=is_unsorted)
        except RaizNoDisponibleError as exc:
            causa = _mensaje_sin_rutas(exc, path)
            report.errors.append(f"{path.name}: {causa}")
            logger.warning("importer.raiz_no_disponible",
                           raiz=exc.raiz, motivo=type(exc).__name__,
                           formato=path.suffix.lstrip(".") or "sin_extension")
            return
        if is_unsorted:
            dest = raiz.path / "_Unsorted" / path.name
        else:
            dest = self._build_dest(
                series_obj, tr, path, base=raiz.path, issue_number=numero_destino)

        # La raíz de DESTINO debe tener espacio antes de copiar; never fallback.
        try:
            await asyncio.to_thread(
                comprobar_espacio, raiz.path, path.stat().st_size, "importar a la biblioteca")
        except EspacioInsuficienteError as exc:
            report.errors.append(f"{path.name}: {_mensaje_sin_rutas(exc, path)}")
            logger.warning("importer.raiz_sin_espacio", raiz=raiz.name,
                           formato=path.suffix.lstrip(".") or "sin_extension")
            return
        except OSError as exc:
            report.errors.append(
                f"{path.name}: no se pudo comprobar el espacio de la raíz: "
                f"{_mensaje_sin_rutas(exc, path)}")
            return

        # A3: mover a destino verificado — nunca sobreescribe y no borra el
        # original hasta que la copia está completa (ver utils/fs.safe_move).
        final_dest = await safe_move_en_raiz_async(path, dest, raiz.path)
        dest_stat = final_dest.stat()

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
        # #307: formato REAL por contenido (file_format sigue siendo la extensión)
        if tr.formato_contenido:
            metadata["formato_contenido"] = tr.formato_contenido

        file_rec = File(
            issue_id=str(result.issue_id) if result.issue_id else None,
            root_id=raiz.id,
            file_path=str(final_dest),
            file_name=final_dest.name,
            file_format=FileFormat(path.suffix.lstrip(".").lower()),
            file_size_bytes=dest_stat.st_size,
            # BL-R9: el stat guardado describe los bytes del hash guardado.
            file_mtime_ns=dest_stat.st_mtime_ns,
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
        if (not is_unsorted and result.issue_id is None and crear_numero
                and numero_destino is not None):
            creado = await self._crear_issue_de_serie_vacia(result, tr, path)
            if creado is not None:
                file_rec.issue_id = result.issue_id
                await self._db.flush()
            else:
                # No se puede dejar un archivo en la carpeta de la serie sin
                # número: se mueve a _Unsorted y se declara Pendientes.
                from zascarr.utils.fs import safe_move_async

                destino_pendiente = raiz.path / "_Unsorted" / final_dest.name
                final_dest = await safe_move_async(final_dest, destino_pendiente)
                file_rec.file_path = str(final_dest)
                file_rec.file_name = final_dest.name
                file_rec.metadata_ = {
                    **(file_rec.metadata_ or {}),
                    "match_status": MatchStatus.UNSORTED.value,
                }
                result.status = MatchStatus.UNSORTED
                result.notes.append("no se pudo crear el número al importar")
                is_unsorted = True
        if result.issue_id is not None and not is_unsorted:
            try:
                await reconciliar_mejora_importada(
                    self._db, result.issue_id, file_rec.id)
            except Exception:  # noqa: BLE001 — la conciliación no tumba la importación
                logger.warning("upgrade.reconciliacion_fallida",
                               issue_id=str(result.issue_id))

        if (getattr(ajustes, "import_convert_cbr", False)
                and not is_unsorted and result.series_id is not None
                and path.suffix.lower() == ".cbr"):
            convertido = await self._convertir_cbr_importado(file_rec, result)
            if convertido is not None:
                final_dest = convertido

        prefijo_raiz = "" if len(foto.raices) <= 1 else f"{raiz.name}: "
        if is_unsorted:
            motivo = "; ".join(result.notes) or "sin match fiable"
            report.unsorted.append(
                f"{path.name} → {prefijo_raiz}_Unsorted ({motivo})")
        else:
            avisos = await self._aplicar_comicinfo(result, tr, final_dest)
            sufijo = f" (ComicInfo: {'; '.join(avisos)})" if avisos else ""
            report.imported.append(
                f"{path.name} → {prefijo_raiz}{final_dest.relative_to(raiz.path)}{sufijo}")
        logger.info("importer.imported", file_id=str(file_rec.id), root=raiz.name,
                    formato=path.suffix.lstrip(".") or "sin_extension",
                    status=result.status)

    async def _aplicar_comicinfo(
            self, result: MatchResult, tr: TriageResult, ruta: Path) -> list[str]:
        """ETQ2: vuelca `<Tags>`/`<Genre>` del ComicInfo en la serie enlazada.

        Solo para importaciones con serie; devuelve los avisos (topes del
        parser y nombres inválidos) para que viajen en el informe del ciclo.
        """
        if result.series_id is None:  # `is_unsorted` ya lo garantiza; defensa
            return []
        if tr.comic_info is None:
            return []
        aplicado = await aplicar_comicinfo(
            self._db, result.series_id,
            tags=tr.comic_info.tags, genres=tr.comic_info.genres,
        )
        if result.issue_id is not None:
            try:
                async with self._db.begin_nested():
                    issue = await self._db.get(Issue, result.issue_id)
                    if issue is not None:
                        await aplicar_a_issue(self._db, issue, ruta)
            except Exception:  # noqa: BLE001, S110 — un XML ajeno no tumba la importación
                pass
        return [*tr.comic_info.warnings, *aplicado.avisos]

    async def _reenlazar(
        self, fila: File, path: Path, tr: TriageResult, report: ImportReport
    ) -> None:
        """El fichero que vuelve a llegar es el mismo contenido que una fila
        `is_missing`: reenlaza esa fila en vez de crear otra o descartar.

        La fila conserva su enlace a Issue/Series y su `original_sha256`; se
        actualizan ruta/nombre/tamaño/hash con los del entrante, se reinicia
        `imported_at` (D8 cierra por `File.imported_at >= Wishlist.added_at`, y
        reactivar un `IMPORTED` reinicia `added_at`) y, si el entrante es el
        ORIGINAL de una fila que estaba etiquetada, se vacían las marcas de
        ComicInfo (`comicinfo_estado`/`comicinfo_propio`), que describen un
        fichero que ya no existe. Cuenta como importado, con «recuperado» para
        distinguirlo (así E4 avisa igual que con una importación normal)."""
        # El destino sale de la fila que YA existe (su Issue/Series), no de un
        # re-match que podría apuntar a otra parte.
        serie: Series | None = None
        numero: str | None = None
        if fila.issue_id:
            fila_issue = (await self._db.execute(
                select(Issue.issue_number, Issue.title, Issue.format, Series)
                .join(Series, Issue.series_id == Series.id)
                .where(Issue.id == fila.issue_id)
            )).first()
            if fila_issue:
                numero, titulo_issue, formato_issue, serie = fila_issue

        try:
            foto, raiz = await self._raiz(
                getattr(serie, "tradition", None), por_defecto=serie is None)
        except RaizNoDisponibleError as exc:
            causa = _mensaje_sin_rutas(exc, path)
            report.errors.append(f"{path.name}: {causa}")
            logger.warning("importer.raiz_no_disponible",
                           raiz=exc.raiz, motivo=type(exc).__name__,
                           formato=path.suffix.lstrip(".") or "sin_extension")
            return
        if serie is None:
            dest = raiz.path / "_Unsorted" / path.name
        else:
            dest = build_library_path(
                raiz.path, serie, numero, path.suffix, fallback_name=path.name,
                issue_title=titulo_issue, issue_format=formato_issue)
        try:
            await asyncio.to_thread(
                comprobar_espacio, raiz.path, path.stat().st_size, "recuperar en la biblioteca")
        except (EspacioInsuficienteError, OSError) as exc:
            report.errors.append(
                f"{path.name}: no se pudo comprobar el espacio: {_mensaje_sin_rutas(exc, path)}")
            return

        # A3: mismo mover verificado que una importación normal.
        final_dest = await safe_move_en_raiz_async(path, dest, raiz.path)

        await _reenlazar_fila(fila, tr, final_dest, root_id=raiz.id)
        await self._db.flush()

        prefijo_raiz = "" if len(foto.raices) <= 1 else f"{raiz.name}: "
        report.imported.append(
            f"{path.name} → {prefijo_raiz}{final_dest.relative_to(raiz.path)} (recuperado)")
        logger.info("importer.recuperado", file_id=str(fila.id), root=raiz.name,
                    formato=path.suffix.lstrip(".") or "sin_extension")

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
                "disparador": report.disparador,
            },
        )
        if report.comprobacion is not None:
            run.details[CLAVE_COMPROBACION] = report.comprobacion.como_dict()
        self._db.add(run)
        await self._db.flush()
        report.run_id = run.id

    async def _serie_tiene_numeros(self, series_id) -> bool:
        """¿La serie ya tiene catálogo? Se consulta antes de mover."""
        return bool((await self._db.execute(
            select(func.count()).select_from(Issue).where(Issue.series_id == series_id)
        )).scalar_one())

    async def _crear_issue_de_serie_vacia(
        self, result: MatchResult, tr: TriageResult, path: Path
    ) -> str | None:
        """B23: si la serie no tiene NINGÚN número, crea el que trae el archivo.

        Solo actúa en una serie vacía: en una catálogo existente, un número que el
        matcher no encontró es una discrepancia que se revisa, no se inventa.
        """
        if result.series_id is None:
            return None
        parsed = parse_comic_filename(path.name, carpeta=path.parent.name)
        numero = (
            (tr.comic_info.number if tr.strong_candidate and tr.comic_info else None)
            or parsed.issue_number
        )
        if not numero or parsed.edition_kind is not None or parsed.is_special or parsed.is_pack:
            return None
        if not tr.strong_candidate and parsed.confidence < 0.7:
            return None
        numero = str(numero).strip()
        if not numero or es_pack(numero):
            return None
        # Serializa la creación por serie y evita que dos importadores creen
        # "1" y "001" como dos filas lógicas distintas.
        await self._db.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
            {"k": f"b23:issue:{result.series_id}"})
        existentes = (await self._db.execute(
            select(func.count()).select_from(Issue)
            .where(Issue.series_id == result.series_id)
        )).scalar_one()
        if existentes:
            return None
        formato = EDITION_KIND_A_FORMAT.get(parsed.edition_kind, IssueFormat.SINGLE_ISSUE)
        try:
            orden = float(numero.replace(",", "."))
        except (TypeError, ValueError):
            orden = None
        issue = Issue(
            series_id=result.series_id, issue_number=numero, format=formato,
            sort_order=orden, metadata_={"origen": "importador"}, locked_fields=[],
        )
        try:
            async with self._db.begin_nested():
                self._db.add(issue)
                await self._db.flush()
        except Exception:  # noqa: BLE001 — carrera con otro importador/alta
            logger.info("importer.issue_nueva_carrera", numero=numero)
            issue = (await self._db.execute(
                select(Issue).where(Issue.series_id == result.series_id,
                                    Issue.issue_number == numero)
            )).scalar_one_or_none()
            if issue is None:
                return None
        result.issue_id = issue.id
        logger.info("importer.issue_creada_al_importar",
                    serie=str(result.series_id), numero=numero)
        return numero

    async def _convertir_cbr_importado(self, file_rec: File,
                                       result: MatchResult) -> Path | None:
        """B23: convierte el CBR importado con la verificación reversible de siempre."""
        if result.series_id is None:
            return None
        try:
            from zascarr.services.conversion import ConversionDeArchivo

            servicio = ConversionDeArchivo(self._db, secret=get_settings().secret_key)
            vista = await servicio.previsualizar(result.series_id, file_rec.id)
            if not vista.puede_convertir or not vista.token:
                logger.info("importer.conversion_omitida",
                            file_id=str(file_rec.id), motivo=vista.motivo)
                return None
            resultado = await servicio.confirmar(vista.token, forzar_compartido=True)
            if resultado.resultado not in ("convertida", "ya_convertida"):
                logger.info("importer.conversion_no_aplicada",
                            file_id=str(file_rec.id), resultado=resultado.resultado)
                return None
            ruta = Path(file_rec.file_path)
            logger.info("importer.conversion_ok", file_id=str(file_rec.id),
                        formato=ruta.suffix.lstrip(".") or "sin_extension")
            return ruta
        except Exception:  # noqa: BLE001 — nunca se pierde el CBR por una conversión
            logger.exception("importer.conversion_fallida", file_id=str(file_rec.id))
            return None

    def _build_dest(self, series, tr: TriageResult, orig: Path, *, base: Path,
                    issue_number: str | None = None) -> Path:
        if not series:
            return base / "_Unsorted" / orig.name
        number = issue_number or (tr.comic_info.number if tr.comic_info else None)
        edition_kind = parse_comic_filename(orig.name).edition_kind
        return build_library_path(
            base, series, number, orig.suffix, fallback_name=orig.name,
            issue_title=getattr(tr.comic_info, "title", None) if tr.comic_info else None,
            issue_format=EDITION_KIND_A_FORMAT.get(edition_kind, IssueFormat.SINGLE_ISSUE),
        )


def build_library_path(library: Path, series: Series, issue_number: str | None,
                       suffix: str, fallback_name: str | None = None,
                       *, issue_title: str | None = None,
                       issue_format: IssueFormat | str | None = None,
                       pack: bool = False, especial: bool = False) -> Path:
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
        ajustes = get_settings()
        if getattr(ajustes, "naming_enabled", False):
            nombre = construir_nombre(
                series, issue_number, titulo=issue_title, formato=issue_format,
                pack=pack or es_pack(issue_number),
                preset=getattr(ajustes, "naming_preset", "clasico"),
                padding=getattr(ajustes, "naming_padding", 0))
            filename = f"{nombre}{suffix}"
        else:
            num = sanitize_segment(str(issue_number)).zfill(3)
            filename = f"{safe_title} #{num}{suffix}"
    else:
        filename = fallback_name or f"{safe_title}{suffix}"
        if especial:
            # Especiales/tomos sin número: van a su propia carpeta dentro de la
            # serie (decisión del PO, 2026-11-16), no al _Unsorted general.
            folder = f"{folder}/Especiales"

    return library / tradition_folder / folder / filename
