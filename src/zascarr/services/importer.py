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
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

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
from zascarr.utils.fs import listar_comics, safe_move_async, sanitize_segment
from zascarr.utils.naming import parse_comic_filename

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


async def _reenlazar_fila(fila: File, tr: TriageResult, dest: Path) -> None:
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
    fila.file_name = dest.name
    fila.file_format = FileFormat(dest.suffix.lstrip(".").lower())
    fila.file_size_bytes = dest.stat().st_size
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
    db: AsyncSession, path: Path, pista: PistaDeCohorte | None = None
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
    parsed = parse_comic_filename(nombre)
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

    result = await matcher.decide(tr, extractor=extractor, formato_esperado=formato_esperado)
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

        # Dedupe por (st_dev, st_ino), no por ruta: ver `listar_comics`. El
        # recorrido va en un hilo — bloquea en E/S (CLAUDE.md §4).
        files = await asyncio.to_thread(listar_comics, self._scan_dirs, COMIC_EXTS)
        report.files_scanned = len(files)

        # Evidencia de cohorte (core/cohort.py): calculada UNA VEZ sobre la
        # foto fija de este ciclo, antes del bucle — contrato de
        # determinismo (2026-09-26): un archivo que llega a mitad de ciclo
        # no puede cambiar la cohorte ya calculada para los anteriores.
        pistas = detectar_ordenes_de_lectura([f.name for f in files])

        for path in sorted(files):
            try:
                await self._import_file(path, report, pistas.get(path.name))
            except CerrojoDeContenidoOcupado:
                # Otra operación (p. ej. un registro de la biblioteca) lleva mucho con el cerrojo:
                # el archivo se queda donde está y se reintenta.
                logger.warning("importer.cerrojo_de_contenido_ocupado")
                report.errors.append(
                    f"{path.name}: otra operación estaba registrando contenido; "
                    "se reintentará en el próximo ciclo")
                # Los demás esperarían lo mismo (60 s cada uno): se corta el recorrido. Siguen en
                # descargas, intactos, y el próximo ciclo los retoma.
                report.errors.append("El ciclo se detuvo antes de mirar el resto de las descargas")
                break
            except Exception as exc:
                logger.exception("importer.file_failed", path=str(path))
                report.errors.append(f"{path.name}: {exc}")

        # B7: revisión de la biblioteca YA importada, no de lo nuevo que
        # acaba de llegar — un paso independiente del bucle de arriba.
        try:
            comprobacion = await self._comprobar_biblioteca()
        except Exception:
            # Un fallo no marca ninguna baja, pero tampoco puede pasar por «no pasó nada»: queda
            # escrito en el informe (#231, criterio 11), sin afirmar causa.
            logger.exception("importer.deteccion_desaparecidos_fallida")
            comprobacion = ComprobacionBiblioteca(
                resultado=ResultadoComprobacion.FALLO_DETECCION, fecha=datetime.now(UTC))
        report.comprobacion = comprobacion
        report.disappeared = comprobacion.desaparecidos
        report.reappeared = comprobacion.reaparecidos

        report.finished_at = datetime.now(UTC)
        await self._persist_run(report)
        return report

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
        """Misma revisión que describe `_detectar_desaparecidos` (B7), pero devolviendo también
        QUÉ observó (#231): el motivo de cada guardarraíl deja de ir solo al log. No cambia cuándo
        se marca una baja ni los umbrales. Una excepción NO se captura aquí: la recoge
        `scan_and_import` y la registra como `FALLO_DETECCION`."""
        fecha = datetime.now(UTC)

        def omitida(resultado, registrados=None, ausentes=None):
            return ComprobacionBiblioteca(resultado=resultado, fecha=fecha,
                                          archivos_registrados=registrados, ausentes=ausentes)

        if not self._library.exists() or not self._library.is_dir():
            logger.warning(
                "importer.biblioteca_inaccesible_omitiendo_desaparecidos", ruta=str(self._library)
            )
            registrados = (await self._db.execute(
                select(func.count()).select_from(File))).scalar_one()
            return omitida(ResultadoComprobacion.RAIZ_INACCESIBLE, registrados)

        files = list((await self._db.execute(select(File))).scalars().all())
        if not files:
            return ComprobacionBiblioteca(resultado=ResultadoComprobacion.COMPROBADA, fecha=fecha,
                                          archivos_registrados=0, ausentes=0)

        biblioteca_vacia = await asyncio.to_thread(lambda: not any(self._library.iterdir()))
        if biblioteca_vacia:
            logger.warning(
                "importer.biblioteca_vacia_omitiendo_desaparecidos", ruta=str(self._library)
            )
            return omitida(ResultadoComprobacion.RAIZ_VACIA, len(files))

        rutas = [f.file_path for f in files]
        # Un único hop a un hilo para todo el lote, no uno por fichero —
        # `stat` es síncrono (I/O bloqueante, CLAUDE.md §4).
        ausentes = await asyncio.to_thread(lambda: {r for r in rutas if not _existe(r)})

        if (
            len(files) >= UMBRAL_DESAPARICION_MASIVA_MINIMO
            and len(ausentes) > len(files) * UMBRAL_DESAPARICION_MASIVA_FRACCION
        ):
            logger.error(
                "importer.desaparicion_masiva_anomala_abortando",
                ausentes=len(ausentes), total_files=len(files), ruta=str(self._library),
            )
            return omitida(ResultadoComprobacion.DESAPARICION_MASIVA, len(files), len(ausentes))

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
        return ComprobacionBiblioteca(
            resultado=ResultadoComprobacion.COMPROBADA, fecha=fecha,
            archivos_registrados=len(files), ausentes=len(ausentes),
            desaparecidos=desaparecidos, reaparecidos=reaparecidos)

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
        # #307: formato REAL por contenido (file_format sigue siendo la extensión)
        if tr.formato_contenido:
            metadata["formato_contenido"] = tr.formato_contenido

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
                select(Issue.issue_number, Series)
                .join(Series, Issue.series_id == Series.id)
                .where(Issue.id == fila.issue_id)
            )).first()
            if fila_issue:
                numero, serie = fila_issue

        if serie is None:
            dest = self._library / "_Unsorted" / path.name
        else:
            dest = build_library_path(
                self._library, serie, numero, path.suffix, fallback_name=path.name)

        # A3: mismo mover verificado que una importación normal.
        final_dest = await safe_move_async(path, dest)

        await _reenlazar_fila(fila, tr, final_dest)
        await self._db.flush()

        report.imported.append(
            f"{path.name} → {final_dest.relative_to(self._library)} (recuperado)")
        logger.info("importer.recuperado", dest=str(final_dest))

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
        if report.comprobacion is not None:
            run.details[CLAVE_COMPROBACION] = report.comprobacion.como_dict()
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
