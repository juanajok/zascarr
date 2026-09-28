"""B6 — servicio de etiquetado: plan por campo y escritura segura de ComicInfo.

Une la BD (qué queremos escribir) con el CBZ (qué hay) y aplica el contrato de
`docs/design/benchmark-B6-comicinfo.md`:

  - un **único** cálculo del plan alimenta la vista previa y la escritura real;
  - el plan **caduca** si el archivo cambia entre calcularlo y aplicarlo;
  - los campos en `locked_fields` (H3) no se pisan, y el informe los cuenta;
  - tras `os.replace` se **recalculan** `sha256_hash`/`file_size_bytes`; si el
    commit falla, la siguiente pasada **reconcilia** el hash en vez de reescribir;
  - CBR/CB7/PDF no se tocan (B20); un error nunca pierde un tebeo.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.comicinfo_write import (
    Accion,
    CampoPlan,
    fusionar_xml,
    hay_cambios,
    leer_campos,
    plan,
)
from zascarr.models import File, FileFormat, Issue, Publisher, Series
from zascarr.utils.cbz import (
    CbzError,
    CbzInvalidoError,
    SinEspacioError,
    VerificacionError,
    leer_comicinfo,
    reescribir_con_xml,
)

logger = structlog.get_logger()

_CHUNK = 256 * 1024

#: tag ComicInfo → (entidad, campo) cuyo `locked_fields` (H3) protege ese tag.
_LOCK_DE: dict[str, tuple[str, str]] = {
    "Series": ("series", "title"),
    "Number": ("issue", "issue_number"),
    "Volume": ("issue", "volume"),
    "Year": ("issue", "release_date"),
    "Publisher": ("series", "publisher_id"),
    "Summary": ("issue", "synopsis"),
}

#: Acciones del informe por lote (ficha, punto 11).
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
    resultados: list[ResultadoEtiquetado] = field(default_factory=list)

    def resumen(self) -> str:
        return (
            f"{self.escritos} escritos, {self.previstos} previstos, "
            f"{self.saltados} ya al día, {self.bloqueados} con campos bloqueados, "
            f"{self.caducados} caducados, {self.invalidos} inválidos, "
            f"{self.sin_espacio} sin espacio, "
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


class TaggerService:
    """Servicio de etiquetado. Un `TaggerService` por sesión; el estado del
    plan vive en el retorno de `planificar()`, no en el objeto."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── contexto desde la BD ────────────────────────────────────────────────

    async def _contexto(self, file: File) -> _Contexto:
        """Valores deseados (mapa mínimo de la ficha) y tags bloqueados (H3).

        `LanguageISO` **nunca** se genera: no se infiere de la tradición."""
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
        issue, series, publisher = row
        deseados = {
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

    # ── el único cálculo del plan ───────────────────────────────────────────

    async def planificar(self, file: File, *, solo_rellenar: bool = False) -> list[CampoPlan]:
        """Calcula el plan campo a campo. Es la **única** función que decide
        qué se escribe: la vista previa y la ejecución la comparten."""
        path = Path(file.file_path)
        xml = await asyncio.to_thread(leer_comicinfo, path)
        root = ElementTree.fromstring(xml) if xml else None
        ctx = await self._contexto(file)
        propio = (file.metadata_ or {}).get("comicinfo_propio") or {}
        campos = plan(leer_campos(root), ctx.deseados, propio, solo_rellenar)
        return [
            CampoPlan(c.tag, Accion.BLOQUEADO, c.actual, c.nuevo)
            if c.accion is Accion.CAMBIA and c.tag in ctx.bloqueados else c
            for c in campos
        ]

    async def _reconciliar(
        self, file: File, path: Path, *, forzar: bool = False, simular: bool = False,
    ) -> bool:
        """Pone `sha256_hash`/`file_size_bytes` de acuerdo con el disco.

        Cubre el caso «el reemplazo salió bien pero el commit falló»: la
        siguiente pasada no reescribe (el XML ya coincide) pero sí corrige la
        BD. Sin `forzar` solo recalcula el hash si el tamaño cambió — hashear
        cada CBZ en cada ciclo es caro en la Pi.

        Con `simular` (vista previa) informa de lo que habría que corregir pero
        **no toca la sesión**: «no escribe nada» vale también para la BD, y una
        sesión reutilizada por quien pidió el `dry-run` no se lleva el cambio
        sin querer."""
        size = path.stat().st_size
        if not forzar and file.file_size_bytes == size:
            return False
        sha = await asyncio.to_thread(_sha256, path)
        if file.sha256_hash == sha and file.file_size_bytes == size:
            return False
        logger.info("tagger.reconciliado", file_id=file.id, path=str(path),
                    simulado=simular)
        if simular:
            return True
        file.sha256_hash = sha
        file.file_size_bytes = size
        await self.db.flush()
        return True

    # ── ejecución ───────────────────────────────────────────────────────────

    async def ejecutar(
        self, file: File, *, dry_run: bool = True, solo_rellenar: bool = False,
        reconciliar_todo: bool = False,
    ) -> ResultadoEtiquetado:
        path = Path(file.file_path)
        if file.file_format is not FileFormat.CBZ:
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO,
                                       motivo="formato no parcheable (solo CBZ)")
        if file.is_missing or not path.exists():
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO,
                                       motivo="archivo ausente")

        estado_antes = await asyncio.to_thread(_estado, path)
        campos = await self.planificar(file, solo_rellenar=solo_rellenar)
        if not hay_cambios(campos):
            reconciliado = await self._reconciliar(
                file, path, forzar=reconciliar_todo, simular=dry_run)
            return ResultadoEtiquetado(file.id, file.file_name, SALTADO, campos,
                                       "ya al día", reconciliado)
        if dry_run:
            return ResultadoEtiquetado(file.id, file.file_name, PREVISTO, campos)

        xml = await asyncio.to_thread(leer_comicinfo, path)
        nuevo = fusionar_xml(xml, campos)

        # El plan caduca si el CBZ cambió entre calcularlo y aplicarlo.
        if await asyncio.to_thread(_estado, path) != estado_antes:
            return ResultadoEtiquetado(file.id, file.file_name, CADUCADO, campos,
                                       "el archivo cambió entre el plan y la escritura")

        try:
            await asyncio.to_thread(reescribir_con_xml, path, nuevo)
        except SinEspacioError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, SIN_ESPACIO, campos, str(exc))
        except VerificacionError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, FALLO_VERIFICACION,
                                       campos, str(exc))
        except CbzInvalidoError as exc:
            return ResultadoEtiquetado(file.id, file.file_name, INVALIDO, campos, str(exc))
        except (CbzError, OSError) as exc:
            return ResultadoEtiquetado(file.id, file.file_name, ERROR, campos, str(exc))

        # El XML cambió los bytes: recalcular hash/tamaño y dejar rastro de
        # autoría (`comicinfo_propio`) para poder aplicar overlay la próxima vez.
        file.sha256_hash = await asyncio.to_thread(_sha256, path)
        file.file_size_bytes = path.stat().st_size
        propio = dict((file.metadata_ or {}).get("comicinfo_propio") or {})
        for c in campos:
            if c.accion is Accion.CAMBIA and c.nuevo:
                propio[c.tag] = c.nuevo
        file.metadata_ = {**(file.metadata_ or {}), "comicinfo_propio": propio}
        await self.db.flush()
        return ResultadoEtiquetado(file.id, file.file_name, ESCRITO, campos)

    # ── lote ────────────────────────────────────────────────────────────────

    async def run(
        self, limit: int = 20, *, dry_run: bool = True, solo_rellenar: bool = False,
        file_ids: list[str] | None = None, reconciliar_todo: bool = False,
    ) -> InformeEtiquetado:
        """Recorre los CBZ con `Issue` enlazado. Con `dry_run=True` no escribe
        nada. `reconciliar_todo` fuerza el recálculo del hash de los que ya
        están al día (costoso en la Pi; para cerrar un commit fallido)."""
        q = (
            select(File)
            .where(File.issue_id.is_not(None))
            .where(File.file_format == FileFormat.CBZ)
            .where(File.is_missing.is_(False))
            .order_by(File.imported_at)
        )
        if file_ids is not None:
            q = q.where(File.id.in_(file_ids))
        elif not reconciliar_todo:
            q = q.limit(limit)
        files = (await self.db.execute(q)).scalars().all()

        informe = InformeEtiquetado()
        for file in files:
            r = await self.ejecutar(file, dry_run=dry_run, solo_rellenar=solo_rellenar,
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
            elif r.accion != SALTADO:
                logger.warning("tagger.accion_desconocida", accion=r.accion, file_id=file.id)
        return informe
