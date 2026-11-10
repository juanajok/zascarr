"""B6 — servicio de etiquetado: plan por campo y escritura segura de ComicInfo.

Une la BD (qué queremos escribir) con el CBZ (qué hay) y aplica el contrato de
`docs/design/benchmark-B6-comicinfo.md`:

  - un **único** cálculo del plan alimenta la vista previa y la escritura real;
  - el plan **caduca** si el archivo cambia entre calcularlo y aplicarlo, y la
    escritura se **serializa por fichero** con un *advisory lock* de PostgreSQL
    por `File.id` (identidad que sobrevive al `os.replace`; un `flock` sobre el
    propio CBZ no lo haría) desde la lectura hasta después del reemplazo;
  - los campos en `locked_fields` (H3) no se pisan, y el informe los cuenta;
  - tras `os.replace` se **recalculan** `sha256_hash`/`file_size_bytes`; si el
    commit falla, la siguiente pasada **reconcilia** aunque el tamaño no cambie;
  - `run()` no vuelve a mirar lo ya revisado: `--limit` acota trabajo **nuevo**,
    no vueltas sobre los mismos ficheros (si no, el nº 21 no llegaría nunca);
  - CBR/CB7/PDF no se tocan (B20); un error nunca pierde un tebeo.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from zascarr.core.comicinfo_write import (
    Accion,
    CampoPlan,
    ComicInfoInvalidoError,
    fusionar_xml,
    hay_cambios,
    leer_campos,
    parsear,
    plan,
)
from zascarr.models import CreatorRole, File, FileFormat, Issue, IssueCreator, Publisher, Series
from zascarr.services.compartidos import estado_de_comparticion
from zascarr.utils import cbz as zcbz
from zascarr.utils.bloqueo_archivo import bloquear_archivo
from zascarr.utils.cbz import (
    CbzError,
    CbzInvalidoError,
    SinEspacioError,
    VerificacionError,
    leer_comicinfo,
)

logger = structlog.get_logger()

_CHUNK = 256 * 1024
#: Filas que se traen por consulta al buscar trabajo pendiente. Se pagina a
#: propósito en vez de usar un cursor de servidor: dentro del bucle se escribe
#: en la BD, y no queremos un resultado abierto sobre la misma conexión.
PAGINA = 200

#: Clave en `File.metadata_` con el resultado de la última revisión.
_ESTADO_KEY = "comicinfo_estado"

#: tag ComicInfo → (entidad, campo) cuyo `locked_fields` (H3) protege ese tag.
_LOCK_DE: dict[str, tuple[str, str]] = {
    "Series": ("series", "title"),
    "Number": ("issue", "issue_number"),
    "Volume": ("issue", "volume"),
    "Year": ("issue", "release_date"),
    "Publisher": ("series", "publisher_id"),
    "Summary": ("issue", "synopsis"),
    # #481: un solo `creators` bloquea los ocho tags de autoría.
    "Writer": ("issue", "creators"),
    "Penciller": ("issue", "creators"),
    "Inker": ("issue", "creators"),
    "Colorist": ("issue", "creators"),
    "Letterer": ("issue", "creators"),
    "CoverArtist": ("issue", "creators"),
    "Editor": ("issue", "creators"),
    "Translator": ("issue", "creators"),
    "Genre": ("series", "genres"),
    "PageCount": ("issue", "page_count"),
}

#: Acciones del informe.
ESCRITO = "escrito"
PREVISTO = "previsto"
SALTADO = "saltado"
CADUCADO = "caducado"
INVALIDO = "invalido"
SIN_ESPACIO = "sin_espacio"
FALLO_VERIFICACION = "fallo_verificacion"
ERROR = "error"


@dataclass
class ResultadoEtiquetado:
    file_id: str
    nombre: str
    accion: str
    campos: list[CampoPlan] = field(default_factory=list)
    motivo: str | None = None
    reconciliado: bool = False
    #: `False` para lo que ni se ha llegado a abrir (fichero ausente): no debe
    #: gastar el cupo de `--limit`, o una biblioteca con rutas rotas dejaría
    #: fuera al resto para siempre.
    gasta_cupo: bool = True
    #: #488: aviso del guardián de compartidos. No impide escribir por sí solo:
    #: el llamante debe pasar `forzar_compartido=True` para aplicar.
    advertencia: str | None = None
    forzado_compartido: bool = False

    def __post_init__(self) -> None:
        # El ORM entrega `File.id` como UUID y esto acaba serializándose a JSON
        # (informe `--json`): se normaliza aquí para que el tipo no mienta.
        self.file_id = str(self.file_id)

    @property
    def bloqueados(self) -> list[CampoPlan]:
        return [c for c in self.campos if c.accion is Accion.BLOQUEADO]


@dataclass
class InformeEtiquetado:
    escritos: int = 0
    previstos: int = 0
    saltados: int = 0
    bloqueados: int = 0
    caducados: int = 0
    invalidos: int = 0
    sin_espacio: int = 0
    fallos_verificacion: int = 0
    errores: int = 0
    reconciliados: int = 0
    #: Ficheros que ni se han abierto por estar ya revisados y sin cambios.
    ya_revisados: int = 0
    #: Motivo por el que se cortó el lote (None si terminó). No es un contador:
    #: si está puesto, el informe NO representa la biblioteca entera.
    abortado: str | None = None
    resultados: list[ResultadoEtiquetado] = field(default_factory=list)

    def resumen(self) -> str:
        return (
            f"{self.escritos} escritos, {self.previstos} previstos, "
            f"{self.saltados} ya al día, {self.ya_revisados} ya revisados antes, "
            f"{self.bloqueados} con campos bloqueados, {self.caducados} caducados, "
            f"{self.invalidos} inválidos, {self.sin_espacio} sin espacio, "
            f"{self.fallos_verificacion} con fallo de verificación, "
            f"{self.errores} con error, {self.reconciliados} reconciliados"
        )


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _estado(path: Path) -> tuple[int, int]:
    """Huella barata del fichero para detectar que el plan caducó."""
    st = path.stat()
    return (st.st_size, st.st_mtime_ns)


def _clave_de(file_id) -> int:
    """Clave del advisory lock de **CBZ** por `File.id`.

    Va en un espacio distinto al de `utils/bloqueo_archivo` (metadata/relación):
    el tagger toma ese lock de metadata en la transacción de su sesión y el de
    CBZ en una conexión dedicada; si ambos usaran la misma clave, la sesión se
    bloquearía a sí misma esperando el lock que ya tiene su otra conexión.
    """
    return int.from_bytes(
        hashlib.blake2b(b"cbz:" + uuid.UUID(str(file_id)).bytes, digest_size=8).digest(),
        "big", signed=True,
    )


def motor_de(db: AsyncSession) -> AsyncEngine:
    """El motor con el que abrir la conexión dedicada del bloqueo.

    Se toma de la propia sesión (`bind`), nunca del motor global: el bloqueo
    tiene que vivir en la MISMA base de datos que las filas que se tocan."""
    bind = db.bind
    if not isinstance(bind, AsyncEngine):
        raise TypeError(
            "el bloqueo por fichero necesita una sesión ligada a un AsyncEngine")
    return bind


@asynccontextmanager
async def bloqueo_de_fichero(
    engine: AsyncEngine, file_id,
) -> AsyncIterator[AsyncConnection]:
    """Serializa la escritura de **este** CBZ entre procesos e instancias.

    Un `flock` sobre el propio fichero no vale: el bloqueo va con el *inodo*, y
    `os.replace` instala uno nuevo. La carrera es real y silenciosa — A bloquea
    el inodo viejo, B se queda esperando ese mismo inodo, A reemplaza la ruta, C
    abre el inodo **nuevo** y entra sin esperar a nadie; cuando A suelta, B
    adquiere el bloqueo de un inodo ya huérfano y B y C reconstruyen la misma
    ruta a la vez, pudiendo además borrarse los temporales entre sí.

    La identidad es el **`File.id`**, que no cambia al reemplazar el fichero.

    Y es `pg_advisory_xact_lock`, **no** `pg_advisory_lock`, sobre una
    **conexión dedicada con su propia transacción corta**:

      - un bloqueo de sesión sobrevive al `ROLLBACK` y solo lo suelta un
        `pg_advisory_unlock` explícito o el fin de la conexión; devolver una
        conexión al pool normalmente la reinicia con `ROLLBACK`, que **no**
        termina necesariamente esa sesión de PostgreSQL, así que un `unlock`
        fallido podría dejar el bloqueo pegado a una conexión reutilizable;
      - un bloqueo de **transacción** lo suelta el `COMMIT`/`ROLLBACK` de esa
        transacción, pase lo que pase con el cuerpo, sin depender de que un
        `unlock` llegue a ejecutarse en una transacción dañada;
      - la conexión es **dedicada** para no meterlo en la transacción larga del
        lote (donde se retendría hasta el commit final).

    Si el proceso muere, la conexión se cierra y PostgreSQL lo suelta solo."""
    clave = _clave_de(file_id)
    async with engine.connect() as conn:
        await conn.execute(
            text("SELECT pg_advisory_xact_lock(:clave)"), {"clave": clave})
        try:
            yield conn
        finally:
            # Terminar ESTA transacción es lo que suelta el bloqueo. Si hasta
            # esto falla, la conexión queda inservible y el pool la descarta:
            # PostgreSQL la cierra y suelta el bloqueo igual.
            with contextlib.suppress(Exception):
                await conn.rollback()


@dataclass
class _Contexto:
    deseados: dict[str, str | None]
    bloqueados: set[str]

    def huella(self) -> dict:
        """Lo que se guarda en la marca: con qué se comparó esta revisión."""
        return {"deseados": self.deseados, "bloqueados": sorted(self.bloqueados)}


_ROLE_A_TAG = {
    CreatorRole.WRITER: "Writer",
    CreatorRole.PENCILER: "Penciller",
    CreatorRole.INKER: "Inker",
    CreatorRole.COLORIST: "Colorist",
    CreatorRole.LETTERER: "Letterer",
    CreatorRole.COVER_ARTIST: "CoverArtist",
    CreatorRole.EDITOR: "Editor",
    CreatorRole.TRANSLATOR: "Translator",
}


def _unir_lista(valores: list[str]) -> str | None:
    """Nombres sin vacíos ni duplicados (casefold), en orden estable."""
    vistos: set[str] = set()
    limpios: list[str] = []
    for valor in sorted((v.strip() for v in valores if v and v.strip()),
                        key=str.casefold):
        clave = valor.casefold()
        if clave in vistos:
            continue
        vistos.add(clave)
        limpios.append(valor)
    return ", ".join(limpios) if limpios else None


def _contexto_de(issue: Issue, series: Series, publisher: Publisher | None) -> _Contexto:
    """Valores deseados (mapa mínimo de la ficha) y tags bloqueados (H3).

    Función **pura** y única: la usan tanto `planificar()` como el criterio de
    «ya revisado», así que no pueden acabar comparando cosas distintas.

    `LanguageISO` **nunca** se genera: no se infiere de la tradición."""
    deseados: dict[str, str | None] = {
        "Series": series.title,
        "Number": issue.issue_number,
        "Volume": str(issue.volume) if issue.volume is not None else None,
        # Year = fecha de publicación DEL EJEMPLAR, nunca Series.start_year.
        "Year": str(issue.release_date.year) if issue.release_date else None,
        "Publisher": publisher.name if publisher is not None else None,
        "Summary": issue.synopsis,
        "LanguageISO": None,
    }
    # #481: autores por rol, géneros de la serie y páginas. `getattr` tolera dobles
    # de prueba sin relaciones cargadas; en producción vienen con selectinload.
    autores: dict[str, list[str]] = {tag: [] for tag in _ROLE_A_TAG.values()}
    for credito in getattr(issue, "credits", None) or []:
        rol = getattr(credito, "role", None)
        tag = _ROLE_A_TAG.get(rol)
        creador = getattr(credito, "creator", None)
        nombre = getattr(creador, "name", None)
        if tag is not None and nombre and str(nombre).strip():
            autores[tag].append(str(nombre).strip())
    for tag, nombres in autores.items():
        deseados[tag] = _unir_lista(nombres)
    generos = [str(getattr(g, "name", "") or "").strip()
               for g in (getattr(series, "genres", None) or [])]
    deseados["Genre"] = _unir_lista(generos)
    deseados["PageCount"] = (str(issue.page_count)
                             if getattr(issue, "page_count", None) is not None else None)
    entidades = {"issue": issue, "series": series}
    bloqueados = {
        tag for tag, (entidad, campo) in _LOCK_DE.items()
        if campo in (entidades[entidad].locked_fields or [])
    }
    return _Contexto(deseados, bloqueados)


class TaggerService:
    """Servicio de etiquetado. Un `TaggerService` por sesión; el estado del
    plan vive en el retorno de `planificar()`, no en el objeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── contexto desde la BD ────────────────────────────────────────────────

    async def _contexto(self, file: File) -> _Contexto:
        if file.issue_id is None:
            return _Contexto({}, set())
        row = (await self.db.execute(
            select(Issue, Series, Publisher)
            .join(Series, Issue.series_id == Series.id)
            .outerjoin(Publisher, Series.publisher_id == Publisher.id)
            .options(
                selectinload(Issue.credits).selectinload(IssueCreator.creator),
                selectinload(Series.genres),
            )
            .where(Issue.id == file.issue_id)
        )).first()
        if row is None:
            return _Contexto({}, set())
        return _contexto_de(*row)

    # ── el único cálculo del plan ───────────────────────────────────────────

    async def planificar(
        self, file: File, ctx: _Contexto | None = None, *, solo_rellenar: bool = False,
    ) -> list[CampoPlan]:
        """Calcula el plan campo a campo. Es la **única** función que decide
        qué se escribe: la vista previa y la ejecución la comparten.

        Lanza `ComicInfoInvalidoError` si el CBZ trae un `ComicInfo.xml` que no
        se puede leer: en ese caso no se toca el fichero."""
        path = Path(file.file_path)
        xml = await asyncio.to_thread(leer_comicinfo, path)
        root = parsear(xml) if xml else None
        ctx = ctx if ctx is not None else await self._contexto(file)
        propio = (file.metadata_ or {}).get("comicinfo_propio") or {}
        campos = plan(leer_campos(root), ctx.deseados, propio, solo_rellenar)
        return [
            CampoPlan(c.tag, Accion.BLOQUEADO, c.actual, c.nuevo)
            if c.accion is Accion.CAMBIA and c.tag in ctx.bloqueados else c
            for c in campos
        ]

    # ── marca de revisión y reconciliación ──────────────────────────────────

    def _marca(self, file: File) -> dict:
        return (file.metadata_ or {}).get(_ESTADO_KEY) or {}

    def _stat_fresco(self, file: File, marca: dict) -> bool:
        """¿Sigue el fichero tal y como estaba cuando se revisó? (un `stat`)."""
        try:
            st = Path(file.file_path).stat()
        except OSError:
            return False
        return marca.get("size") == st.st_size and marca.get("mtime_ns") == st.st_mtime_ns

    def _ya_revisado(self, file: File, ctx: _Contexto) -> bool:
        """Criterio **persistente** de pendientes, no una ventana a ciegas.

        Un fichero está al día si su contenido no ha cambiado desde la última
        revisión **y** los datos de la BD con los que se comparó son los de
        ahora. Así `--limit` acota trabajo nuevo y no vuelve siempre sobre los
        mismos: sin esto, el fichero nº 21 no recibiría nunca su turno.

        Un `ComicInfo.xml` inválido también se marca (si no, ocuparía el cupo
        para siempre), y se vuelve a mirar en cuanto el fichero cambie."""
        marca = self._marca(file)
        if not marca or not self._stat_fresco(file, marca):
            return False
        if marca.get("resultado") == INVALIDO:
            return True
        return (
            marca.get("hash") == file.sha256_hash
            and marca.get("size") == file.file_size_bytes
            and marca.get("deseados") == ctx.deseados
            and marca.get("bloqueados") == sorted(ctx.bloqueados)
        )

    def _poner_marca(
        self, file: File, ctx: _Contexto, st, sha: str, resultado: str,
    ) -> None:
        file.metadata_ = {
            **(file.metadata_ or {}), _ESTADO_KEY: {
                "resultado": resultado,
                "hash": sha,
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "revisado_en": datetime.now(UTC).isoformat(timespec="seconds"),
                **ctx.huella(),
            },
        }

    async def _sincronizar(
        self, file: File, ctx: _Contexto, path: Path, *, forzar: bool = False,
        simular: bool = False,
    ) -> bool:
        """Deja `sha256_hash`/`file_size_bytes` de acuerdo con el disco y anota
        la revisión. Devuelve si hubo que corregir la BD.

        Cubre el caso «el reemplazo salió bien pero el commit falló»: el XML ya
        coincide, así que no se reescribe, pero la BD se corrige. Se comprueba
        con el `stat` antes de gastar un SHA256 — que es lo que permite detectar
        un reemplazo **del mismo tamaño**, donde mirar solo el tamaño no basta.

        Con `simular` (vista previa) informa pero no toca ni la sesión ni la
        marca: «no escribe nada» vale también para la BD."""
        st = await asyncio.to_thread(path.stat)
        marca = self._marca(file)
        confiable = (
            not forzar
            and marca.get("size") == st.st_size
            and marca.get("mtime_ns") == st.st_mtime_ns
            and marca.get("hash") == file.sha256_hash
            and file.file_size_bytes == st.st_size
        )
        reconciliado = False
        sha = file.sha256_hash
        if not confiable:
            sha = await asyncio.to_thread(_sha256, path)
            if sha != file.sha256_hash or file.file_size_bytes != st.st_size:
                reconciliado = True
                if not simular:
                    logger.info("tagger.reconciliado", file_id=file.id, path=str(path))
                    file.sha256_hash = sha
                    file.file_size_bytes = st.st_size
                    file.file_mtime_ns = st.st_mtime_ns  # BL-R9: el stat describe el hash
        if not simular:
            self._poner_marca(file, ctx, st, sha, SALTADO)
        return reconciliado

    # ── ejecución ───────────────────────────────────────────────────────────

    async def ejecutar(
        self, file: File, *, dry_run: bool = True, solo_rellenar: bool = False,
        reconciliar_todo: bool = False, forzar_compartido: bool = False,
    ) -> ResultadoEtiquetado:
        """Evalúa **siempre** este fichero (no consulta la marca de revisión:
        eso lo hace `run()` para acotar el lote)."""
        return await self._ejecutar_con(
            file, await self._contexto(file), Path(file.file_path),
            dry_run=dry_run, solo_rellenar=solo_rellenar,
            reconciliar_todo=reconciliar_todo,
            forzar_compartido=forzar_compartido)

    async def _advertencia_por_compartido(self, file: File, path: Path) -> str | None:
        """#488: aviso del guardián (solo lectura). El tagger/CLI decide si continuar."""
        decision = await estado_de_comparticion(path)
        if not decision.bloquea:
            return None
        logger.info("tagger.compartido_advierte", file_id=file.id,
                    estado=decision.estado.value)
        return (
            f"{decision.mensaje} Si escribes de todos modos, Transmission/aMule pueden dejar de "
            "compartir bien este archivo. Para continuar hace falta una confirmación explícita "
            "(--forzar en el comando)."
        )

    async def _ejecutar_con(
        self, file: File, ctx: _Contexto, path: Path, *,
        dry_run: bool, solo_rellenar: bool, reconciliar_todo: bool,
        forzar_compartido: bool = False,
    ) -> ResultadoEtiquetado:
        # Guarda barata de formato (también la usa el constructor de pruebas sin
        # sesión); para la escritura real se vuelve a comprobar tras releer.
        if file.file_format is not FileFormat.CBZ:
            return ResultadoEtiquetado(
                file.id, file.file_name, SALTADO,
                motivo="formato no parcheable (solo CBZ)", gasta_cupo=False)
        # Vista previa: puede usar lo cargado antes (no escribe).
        if dry_run:
            if file.is_missing or not path.exists():
                return ResultadoEtiquetado(
                    file.id, file.file_name, SALTADO,
                    motivo="archivo ausente", gasta_cupo=False)
            advertencia = await self._advertencia_por_compartido(file, path)
            resultado = await self._simular(file, ctx, path, solo_rellenar, reconciliar_todo)
            if advertencia is not None:
                resultado.advertencia = advertencia
            return resultado

        # Escritura real. Dos locks por `File.id`, con espacios distintos:
        #  - `bloquear_archivo` en la transacción de la SESIÓN (la que escribe
        #    `metadata_`): se mantiene hasta el commit/rollback del lote, así
        #    rescan/mantener/asignación no pueden leer una versión anterior
        #    entre el flush y el commit.
        #  - `bloqueo_de_fichero` en una conexión dedicada para el reemplazo
        #    atómico del CBZ; no debe ser la misma clave que el de arriba o la
        #    sesión esperaría un lock de su propia otra conexión.
        await bloquear_archivo(self.db, file.id)
        async with bloqueo_de_fichero(motor_de(self.db), file.id):
            # Releer DESPUÉS de ambos locks: el `file`/`ctx`/`path` recibidos se
            # cargaron antes y pueden estar obsoletos (otra operación pudo
            # cambiar la relación, la ruta o `metadata_`).
            fresco = (await self.db.execute(
                select(File).where(File.id == file.id).execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if fresco is None:
                return ResultadoEtiquetado(
                    file.id, file.file_name, SALTADO,
                    motivo="archivo ya no está en la BD", gasta_cupo=False)
            file = fresco
            path = Path(file.file_path)
            ctx = await self._contexto(file)
            if file.file_format is not FileFormat.CBZ:
                return ResultadoEtiquetado(
                    file.id, file.file_name, SALTADO,
                    motivo="formato no parcheable (solo CBZ)", gasta_cupo=False)
            if file.is_missing or not path.exists():
                return ResultadoEtiquetado(
                    file.id, file.file_name, SALTADO,
                    motivo="archivo ausente", gasta_cupo=False)
            advertencia = await self._advertencia_por_compartido(file, path)
            if advertencia is not None and not forzar_compartido:
                return ResultadoEtiquetado(
                    file.id, file.file_name, SALTADO,
                    motivo=advertencia, gasta_cupo=False, advertencia=advertencia)
            resultado = await self._escribir(
                file, ctx, path, solo_rellenar, reconciliar_todo)
            if advertencia is not None:
                resultado.advertencia = advertencia
                resultado.forzado_compartido = True
            await self.db.flush()
        # El lock de la sesión sigue vivo hasta que el llamante haga commit/rollback.
        return resultado

    async def _sesion_utilizable(self) -> bool:
        """Tras un fallo, ¿la sesión sigue sirviendo? (un `SELECT 1`).

        Un `flush()` fallido deja la transacción abortada y SQLAlchemy exige un
        `rollback()` completo antes de reutilizar la sesión. Se comprueba en vez
        de suponerlo: de eso depende cortar el lote o poder seguir."""
        try:
            await self.db.execute(text("SELECT 1"))
            return True
        except Exception:  # noqa: BLE001 — cualquier cosa = no recuperable
            return False

    async def _simular(
        self, file: File, ctx: _Contexto, path: Path,
        solo_rellenar: bool, reconciliar_todo: bool,
    ) -> ResultadoEtiquetado:
        try:
            campos = await self.planificar(file, ctx, solo_rellenar=solo_rellenar)
        except ComicInfoInvalidoError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, [],
                                       f"ComicInfo.xml inválido: {exc}")
        if not hay_cambios(campos):
            reconciliado = await self._sincronizar(
                file, ctx, path, forzar=reconciliar_todo, simular=True)
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO, campos,
                                       "ya al día", reconciliado)
        return ResultadoEtiquetado(file.id, file.file_name, PREVISTO, campos)

    async def _escribir(
        self, file: File, ctx: _Contexto, path: Path,
        solo_rellenar: bool, reconciliar_todo: bool,
    ) -> ResultadoEtiquetado:
        estado_antes = await asyncio.to_thread(_estado, path)
        try:
            campos = await self.planificar(file, ctx, solo_rellenar=solo_rellenar)
        except ComicInfoInvalidoError as exc:
            st = await asyncio.to_thread(path.stat)
            self._poner_marca(file, ctx, st, file.sha256_hash or "", INVALIDO)
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, [],
                                       f"ComicInfo.xml inválido: {exc}")
        if not hay_cambios(campos):
            reconciliado = await self._sincronizar(
                file, ctx, path, forzar=reconciliar_todo)
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO, campos,
                                       "ya al día", reconciliado)

        # El plan ya leyó este XML sin error: si ahora falla (tope, XML ilegible) es que el CBZ
        # cambió entre medias. Se trata como plan caducado y no se toca el fichero.
        try:
            xml = await asyncio.to_thread(leer_comicinfo, path)
            nuevo = fusionar_xml(xml, campos)
        except ComicInfoInvalidoError:
            return ResultadoEtiquetado(file.id, file.file_name, CADUCADO, campos,
                                       "el archivo cambió entre el plan y la escritura")

        # El plan caduca si el CBZ cambió entre calcularlo y aplicarlo.
        if await asyncio.to_thread(_estado, path) != estado_antes:
            return ResultadoEtiquetado(file.id, file.file_name, CADUCADO, campos,
                                       "el archivo cambió entre el plan y la escritura")

        # Integridad (benchmark-integridad-hash-dedupe): el hash ORIGINAL
        # (pre-reemplazo) se captura ANTES de reescribir — después los bytes ya
        # son otros. Solo la primera vez (si ya está fijado, no se toca). Sale
        # de la BD si ésta coincide con el disco (por tamaño); si no, se calcula
        # del disco justo antes de reemplazar. Cero hashes extra en el caso
        # normal.
        #
        # `comicinfo_propio` solo lo rellena el tagger: si ya tiene contenido,
        # es un CBZ etiquetado ANTES de la migración 0016 y su original se
        # perdió — no se inventa con el hash del fichero ya etiquetado (que
        # además quedaría desfasado tras el siguiente reemplazo).
        original_para_guardar: str | None = None
        if file.original_sha256 is None and not (file.metadata_ or {}).get("comicinfo_propio"):
            if file.sha256_hash is not None and file.file_size_bytes == estado_antes[0]:
                original_para_guardar = file.sha256_hash
            else:
                original_para_guardar = await asyncio.to_thread(_sha256, path)

        try:
            await asyncio.to_thread(zcbz.reescribir_con_xml, path, nuevo)
        except SinEspacioError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, SIN_ESPACIO, campos, str(exc))
        except VerificacionError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, FALLO_VERIFICACION,
                                       campos, str(exc))
        except CbzInvalidoError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, campos, str(exc))
        except (CbzError, OSError) as exc:
            return ResultadoEtiquetado(file.id, file.file_name, ERROR, campos, str(exc))

        return await self._anotar_escritura(file, ctx, path, campos, original_para_guardar)

    async def aplicar_plan(
        self, file: File, campos: list[CampoPlan], *, estado_antes: tuple[int, int] | None = None,
    ) -> ResultadoEtiquetado:
        """#480: aplica EXACTAMENTE un plan ya calculado (vista previa firmada).

        No vuelve a planificar ni consulta fuentes: lee el XML, fusiona solo esos campos, verifica
        que el CBZ no cambió desde `estado_antes` y anota la escritura igual que B6. El llamante
        mantiene los locks de `File.id` y el guardián de compartidos.
        """
        ctx = await self._contexto(file)
        path = Path(file.file_path)
        if any(c.accion is Accion.CAMBIA and c.tag in ctx.bloqueados for c in campos):
            return ResultadoEtiquetado(file.id, file.file_name, CADUCADO, campos,
                                       "hay un campo bloqueado nuevo; vuelve a la vista previa")
        if estado_antes is None:
            estado_antes = await asyncio.to_thread(_estado, path)
        if await asyncio.to_thread(_estado, path) != estado_antes:
            return ResultadoEtiquetado(
                file.id, file.file_name, CADUCADO, campos,
                "el archivo cambió desde la vista previa")
        if not hay_cambios(campos):
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO, campos, "ya al día")
        try:
            xml = await asyncio.to_thread(leer_comicinfo, path)
            nuevo = fusionar_xml(xml, campos)
        except ComicInfoInvalidoError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, campos,
                                       f"ComicInfo.xml inválido: {exc}")
        original_para_guardar: str | None = None
        if file.original_sha256 is None and not (file.metadata_ or {}).get("comicinfo_propio"):
            if file.sha256_hash is not None and file.file_size_bytes == estado_antes[0]:
                original_para_guardar = file.sha256_hash
            else:
                original_para_guardar = await asyncio.to_thread(_sha256, path)
        try:
            await asyncio.to_thread(zcbz.reescribir_con_xml, path, nuevo)
        except SinEspacioError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, SIN_ESPACIO, campos, str(exc))
        except VerificacionError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, FALLO_VERIFICACION,
                                       campos, str(exc))
        except CbzInvalidoError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, campos, str(exc))
        except (CbzError, OSError) as exc:
            return ResultadoEtiquetado(file.id, file.file_name, ERROR, campos, str(exc))
        return await self._anotar_escritura(file, ctx, path, campos, original_para_guardar)

    async def _anotar_escritura(
        self, file: File, ctx: _Contexto, path: Path, campos: list[CampoPlan],
        original_para_guardar: str | None = None,
    ) -> ResultadoEtiquetado:
        """El XML cambió los bytes: recalcular hash/tamaño, dejar rastro de
        autoría (`comicinfo_propio`, para poder aplicar overlay la próxima vez)
        y anotar la revisión. `original_para_guardar` es el hash pre-reemplazo:
        se fija en `original_sha256` solo la primera vez."""
        st = await asyncio.to_thread(path.stat)
        sha = await asyncio.to_thread(_sha256, path)
        file.sha256_hash = sha
        file.file_size_bytes = st.st_size
        file.file_mtime_ns = st.st_mtime_ns  # BL-R9: el stat describe el hash
        if original_para_guardar is not None and file.original_sha256 is None:
            file.original_sha256 = original_para_guardar
        propio = dict((file.metadata_ or {}).get("comicinfo_propio") or {})
        for c in campos:
            if c.accion is Accion.CAMBIA and c.nuevo:
                propio[c.tag] = c.nuevo
        file.metadata_ = {**(file.metadata_ or {}), "comicinfo_propio": propio}
        self._poner_marca(file, ctx, st, sha, ESCRITO)
        return ResultadoEtiquetado(file.id, file.file_name, ESCRITO, campos)

    # ── lote ────────────────────────────────────────────────────────────────

    def _consulta(self, file_ids: list[str] | None):
        q = (
            select(File, Issue, Series, Publisher)
            .join(Issue, File.issue_id == Issue.id)
            .join(Series, Issue.series_id == Series.id)
            .outerjoin(Publisher, Series.publisher_id == Publisher.id)
            .options(
                selectinload(Issue.credits).selectinload(IssueCreator.creator),
                selectinload(Series.genres),
            )
            .where(File.file_format == FileFormat.CBZ)
            .where(File.is_missing.is_(False))
            # Orden GLOBAL por `File.id` (y no por imported_at): rescan ordena
            # igual sus cambios y los advisory locks se piden en el mismo orden.
            # Sin esto, dos procesos multi-fichero podían tomar A/B en órdenes
            # opuestos y bloquearse mutuamente.
            .order_by(File.id)
        )
        if file_ids is not None:
            q = q.where(File.id.in_(file_ids))
        return q

    async def _pendientes(self, file_ids: list[str] | None):
        """Filas elegibles, por páginas de `PAGINA`.

        Se pagina a propósito en vez de dejar abierto un cursor de servidor:
        dentro del bucle se escribe en la BD y no queremos dos operaciones
        simultáneas sobre la misma conexión."""
        ultimo = None
        while True:
            q = self._consulta(file_ids).limit(PAGINA)
            if ultimo is not None:
                q = q.where(File.id > ultimo)
            filas = (await self.db.execute(q)).all()
            if not filas:
                return
            for fila in filas:
                yield fila
            if len(filas) < PAGINA:
                return
            ultimo = filas[-1][0].id

    async def run(
        self, limit: int = 20, *, dry_run: bool = True, solo_rellenar: bool = False,
        file_ids: list[str] | None = None, reconciliar_todo: bool = False,
        forzar_compartido: bool = False,
    ) -> InformeEtiquetado:
        """Recorre los CBZ con `Issue` enlazado y evalúa solo lo pendiente.

        `limit` acota el trabajo **nuevo** de cada pasada (0 o menos = sin
        límite): lo ya revisado y sin cambios no gasta cupo, así que repetir
        `--limit 20` avanza de verdad en vez de mirar siempre los mismos 20.
        `reconciliar_todo` ignora esa marca (y fuerza el recálculo del hash).
        Con `dry_run=True` no se escribe ni en el CBZ ni en la BD."""
        informe = InformeEtiquetado()
        sin_limite = limit is None or limit <= 0
        # Con `--file-id` el coleccionista pregunta por ficheros concretos:
        # aunque estén ya revisados, se detallan.
        detallar = file_ids is not None
        procesados = 0

        async for fila in self._pendientes(file_ids):
            file, issue, series, publisher = fila
            ctx = _contexto_de(issue, series, publisher)
            if not reconciliar_todo and self._ya_revisado(file, ctx):
                informe.ya_revisados += 1
                if detallar:
                    informe.resultados.append(ResultadoEtiquetado(
                        file.id, file.file_name, SALTADO, [],
                        "ya revisado (sin cambios desde la última pasada)"))
                continue
            try:
                r = await self._ejecutar_con(file, ctx, Path(file.file_path),
                                             dry_run=dry_run,
                                             solo_rellenar=solo_rellenar,
                                             reconciliar_todo=reconciliar_todo,
                                             forzar_compartido=forzar_compartido)
                sesion_rota = False
            except Exception as exc:  # noqa: BLE001
                logger.exception("tagger.fallo_inesperado", file_id=file.id)
                r = ResultadoEtiquetado(file.id, file.file_name, ERROR, [], str(exc))
                # Un error sin más se apunta y se sigue. Pero si la sesión ha
                # quedado inservible, los siguientes fallarían todos por la
                # misma razón: se corta y se dice, en vez de encadenar errores
                # fingiendo que la pasada salió bien.
                sesion_rota = not await self._sesion_utilizable()
            if r.bloqueados:
                informe.bloqueados += 1
            informe.resultados.append(r)
            if r.reconciliado:
                informe.reconciliados += 1
            contador = {
                ESCRITO: "escritos", PREVISTO: "previstos", SALTADO: "saltados",
                CADUCADO: "caducados", INVALIDO: "invalidos",
                SIN_ESPACIO: "sin_espacio", FALLO_VERIFICACION: "fallos_verificacion",
                ERROR: "errores",
            }.get(r.accion)
            if contador:
                setattr(informe, contador, getattr(informe, contador) + 1)
            else:
                logger.warning("tagger.accion_desconocida", accion=r.accion, file_id=file.id)
            if sesion_rota:
                with contextlib.suppress(Exception):
                    await self.db.rollback()
                informe.abortado = (
                    f"la sesión de BD no se recupera tras el fallo ({r.motivo}); "
                    f"{informe.escritos} ficheros ya sustituidos en disco quedan "
                    f"con la fila de `File` sin actualizar y se reconcilian solos "
                    f"en la siguiente pasada")
                logger.error("tagger.lote_abortado", escritos=informe.escritos,
                             motivo=r.motivo)
                break
            if r.gasta_cupo:
                procesados += 1
                if not sin_limite and procesados >= limit:
                    break
        return informe
