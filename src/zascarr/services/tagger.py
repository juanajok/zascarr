"""B6 — servicio de etiquetado: plan por campo y escritura segura de ComicInfo.

Une la BD (qué queremos escribir) con el CBZ (qué hay) y aplica el contrato de
`docs/design/benchmark-B6-comicinfo.md`:

  - un **único** cálculo del plan alimenta la vista previa y la escritura real;
  - el plan **caduca** si el archivo cambia entre calcularlo y aplicarlo, y la
    escritura se **serializa por fichero** (bloqueo exclusivo desde la lectura
    hasta después del `os.replace`);
  - los campos en `locked_fields` (H3) no se pisan, y el informe los cuenta;
  - tras `os.replace` se **recalculan** `sha256_hash`/`file_size_bytes`; si el
    commit falla, la siguiente pasada **reconcilia** aunque el tamaño no cambie;
  - `run()` no vuelve a mirar lo ya revisado: `--limit` acota trabajo **nuevo**,
    no vueltas sobre los mismos ficheros (si no, el nº 21 no llegaría nunca);
  - CBR/CB7/PDF no se tocan (B20); un error nunca pierde un tebeo.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import structlog
from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

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
from zascarr.models import File, FileFormat, Issue, Publisher, Series
from zascarr.utils import cbz as zcbz
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


@dataclass
class _Contexto:
    deseados: dict[str, str | None]
    bloqueados: set[str]

    def huella(self) -> dict:
        """Lo que se guarda en la marca: con qué se comparó esta revisión."""
        return {"deseados": self.deseados, "bloqueados": sorted(self.bloqueados)}


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
        if not simular:
            self._poner_marca(file, ctx, st, sha, SALTADO)
            await self.db.flush()
        return reconciliado

    # ── ejecución ───────────────────────────────────────────────────────────

    async def ejecutar(
        self, file: File, *, dry_run: bool = True, solo_rellenar: bool = False,
        reconciliar_todo: bool = False,
    ) -> ResultadoEtiquetado:
        """Evalúa **siempre** este fichero (no consulta la marca de revisión:
        eso lo hace `run()` para acotar el lote)."""
        return await self._ejecutar_con(
            file, await self._contexto(file), Path(file.file_path),
            dry_run=dry_run, solo_rellenar=solo_rellenar,
            reconciliar_todo=reconciliar_todo)

    async def _ejecutar_con(
        self, file: File, ctx: _Contexto, path: Path, *,
        dry_run: bool, solo_rellenar: bool, reconciliar_todo: bool,
    ) -> ResultadoEtiquetado:
        # Guardas comunes a `ejecutar()` y `run()`: un fichero que ya no está
        # (borrado a mano, disco de red caído) se salta, nunca aborta el lote.
        if file.file_format is not FileFormat.CBZ:
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO,
                                       motivo="formato no parcheable (solo CBZ)",
                                       gasta_cupo=False)
        if file.is_missing or not path.exists():
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO,
                                       motivo="archivo ausente", gasta_cupo=False)
        if dry_run:
            return await self._simular(file, ctx, path, solo_rellenar, reconciliar_todo)

        # Escritura real: bloqueo exclusivo desde la lectura/plan hasta después
        # del reemplazo. Dos etiquetados del mismo tebeo no pueden intercalarse.
        try:
            fd = await asyncio.to_thread(zcbz.abrir_bloqueado, path)
        except OSError as exc:  # desapareció entre la consulta y el bloqueo
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO,
                                       motivo=f"archivo ausente: {exc}",
                                       gasta_cupo=False)
        try:
            return await self._escribir(file, ctx, path, solo_rellenar, reconciliar_todo)
        finally:
            await asyncio.to_thread(zcbz.cerrar_bloqueado, fd)

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
            await self.db.flush()
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, [],
                                       f"ComicInfo.xml inválido: {exc}")
        if not hay_cambios(campos):
            reconciliado = await self._sincronizar(
                file, ctx, path, forzar=reconciliar_todo)
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO, campos,
                                       "ya al día", reconciliado)

        xml = await asyncio.to_thread(leer_comicinfo, path)
        nuevo = fusionar_xml(xml, campos)

        # El plan caduca si el CBZ cambió entre calcularlo y aplicarlo.
        if await asyncio.to_thread(_estado, path) != estado_antes:
            return ResultadoEtiquetado(file.id, file.file_name, CADUCADO, campos,
                                       "el archivo cambió entre el plan y la escritura")

        try:
            await asyncio.to_thread(zcbz.reescribir_con_xml, path, nuevo,
                                    ya_bloqueado=True)
        except SinEspacioError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, SIN_ESPACIO, campos, str(exc))
        except VerificacionError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, FALLO_VERIFICACION,
                                       campos, str(exc))
        except CbzInvalidoError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, campos, str(exc))
        except (CbzError, OSError) as exc:
            return ResultadoEtiquetado(file.id, file.file_name, ERROR, campos, str(exc))

        return await self._anotar_escritura(file, ctx, path, campos)

    async def _anotar_escritura(
        self, file: File, ctx: _Contexto, path: Path, campos: list[CampoPlan],
    ) -> ResultadoEtiquetado:
        """El XML cambió los bytes: recalcular hash/tamaño, dejar rastro de
        autoría (`comicinfo_propio`, para poder aplicar overlay la próxima vez)
        y anotar la revisión."""
        st = await asyncio.to_thread(path.stat)
        sha = await asyncio.to_thread(_sha256, path)
        file.sha256_hash = sha
        file.file_size_bytes = st.st_size
        propio = dict((file.metadata_ or {}).get("comicinfo_propio") or {})
        for c in campos:
            if c.accion is Accion.CAMBIA and c.nuevo:
                propio[c.tag] = c.nuevo
        file.metadata_ = {**(file.metadata_ or {}), "comicinfo_propio": propio}
        self._poner_marca(file, ctx, st, sha, ESCRITO)
        await self.db.flush()
        return ResultadoEtiquetado(file.id, file.file_name, ESCRITO, campos)

    # ── lote ────────────────────────────────────────────────────────────────

    def _consulta(self, file_ids: list[str] | None):
        q = (
            select(File, Issue, Series, Publisher)
            .join(Issue, File.issue_id == Issue.id)
            .join(Series, Issue.series_id == Series.id)
            .outerjoin(Publisher, Series.publisher_id == Publisher.id)
            .where(File.file_format == FileFormat.CBZ)
            .where(File.is_missing.is_(False))
            .order_by(File.imported_at, File.id)
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
                q = q.where(tuple_(File.imported_at, File.id) > tuple_(*ultimo))
            filas = (await self.db.execute(q)).all()
            if not filas:
                return
            for fila in filas:
                yield fila
            if len(filas) < PAGINA:
                return
            ultimo = (filas[-1][0].imported_at, filas[-1][0].id)

    async def run(
        self, limit: int = 20, *, dry_run: bool = True, solo_rellenar: bool = False,
        file_ids: list[str] | None = None, reconciliar_todo: bool = False,
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
            r = await self._ejecutar_con(file, ctx, Path(file.file_path),
                                         dry_run=dry_run,
                                         solo_rellenar=solo_rellenar,
                                         reconciliar_todo=reconciliar_todo)
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
            if r.gasta_cupo:
                procesados += 1
                if not sin_limite and procesados >= limit:
                    break
        return informe
