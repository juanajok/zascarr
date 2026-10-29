# ruff: noqa: E501
"""Qué archivos no están disponibles y qué comprobó el último ciclo (BL-R2, #231).

SOLO LECTURA, sin tocar el disco: ni `Path.exists()` ni nada parecido (decisión del PO, 2026-10-24).
Lo que se muestra son observaciones que el ciclo del importador ya dejó escritas:

- el **estado conocido** de cada archivo (`files.is_missing`, `files.missing_since`);
- el **resultado de la última comprobación** de la biblioteca (`import_runs.details["comprobacion_biblioteca"]`),
  que distingue «se miró cada ruta» de «no se pudo mirar» y de «un guardarraíl evitó dar bajas»;
- la **vigencia** de esa evidencia: la fecha de la última comprobación que sí se completó.

Nunca se afirma una causa (disco desmontado, archivos perdidos): solo lo observado. Un ciclo anterior a esta
función no trae la clave y se lee como «sin dato»; `missing_since` no sustituye jamás a la fecha de comprobación.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.models import File, ImportRun, Issue, ResultadoComprobacion, Series

#: Clave de `import_runs.details`. La escribe `services/importer.py` (`CLAVE_COMPROBACION`); se repite aquí
#: para que esta lectura no importe el importador entero (que arrastra el matcher y el triaje).
CLAVE_COMPROBACION = "comprobacion_biblioteca"
LIMITE_PAGINA = 100


@dataclass(frozen=True)
class EstadoComprobacion:
    """La última comprobación conocida. `resultado is None` = «Sin dato de última comprobación válida»."""
    resultado: ResultadoComprobacion | None = None
    fecha: datetime | None = None  # cuándo hizo el ciclo ESA comprobación
    archivos_registrados: int | None = None
    ausentes: int | None = None
    ultima_valida: datetime | None = None  # fecha de la última con resultado `comprobada`, si consta

    @property
    def sin_dato(self) -> bool:
        return self.resultado is None

    @property
    def sin_verificar(self) -> bool:
        """La disponibilidad actual NO está verificada: el ciclo no pudo (o no quiso fiarse de) mirar las rutas."""
        return self.resultado is not None and self.resultado is not ResultadoComprobacion.COMPROBADA

    @property
    def comprobada(self) -> bool:
        return self.resultado is ResultadoComprobacion.COMPROBADA


@dataclass(frozen=True)
class ArchivoNoDisponible:
    id: str
    nombre: str
    desde: datetime | None  # `missing_since`; None si no consta
    serie: str | None  # None si el archivo no está vinculado (p. ej. tras desvincularlo, ADR 0014)
    numero: str | None


@dataclass(frozen=True)
class PaginaNoDisponibles:
    archivos: list[ArchivoNoDisponible]
    total: int
    #: Token para pedir la página siguiente; `None` si esta es la última.
    siguiente: str | None


def _fecha(valor: object) -> datetime | None:
    if not isinstance(valor, str):
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _resultado(valor: object) -> ResultadoComprobacion | None:
    try:
        return ResultadoComprobacion(valor)  # type: ignore[arg-type]
    except ValueError:
        return None


def _entero(valor: object) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def _ciclos_del_importador():
    """Los `ImportRun` del importador: los de auditoría, adopción y registro llevan `details["kind"]`."""
    return ImportRun.details["kind"].astext.is_(None)


async def ultima_comprobacion(db: AsyncSession) -> EstadoComprobacion:
    """Resultado del ÚLTIMO ciclo del importador y fecha de la última comprobación completa.

    Dos consultas de una fila cada una. Si el último ciclo es anterior a #231 (sin la clave) devuelve «sin dato»,
    aunque exista una comprobación completa más antigua: no se reconstruye nada que ese ciclo no registró."""
    ultimo = (await db.execute(
        select(ImportRun.details[CLAVE_COMPROBACION])
        .where(_ciclos_del_importador())
        .order_by(ImportRun.started_at.desc()).limit(1))).first()
    datos = ultimo[0] if ultimo else None
    if not isinstance(datos, dict) or (resultado := _resultado(datos.get("resultado"))) is None:
        return EstadoComprobacion()

    valida = (await db.execute(
        select(ImportRun.details[CLAVE_COMPROBACION]["fecha"].astext)
        .where(_ciclos_del_importador(),
               ImportRun.details[CLAVE_COMPROBACION]["resultado"].astext == ResultadoComprobacion.COMPROBADA.value)
        .order_by(ImportRun.started_at.desc()).limit(1))).first()
    return EstadoComprobacion(
        resultado=resultado, fecha=_fecha(datos.get("fecha")),
        archivos_registrados=_entero(datos.get("archivos_registrados")), ausentes=_entero(datos.get("ausentes")),
        ultima_valida=_fecha(valida[0]) if valida else None)


@dataclass(frozen=True)
class UltimaEjecucionImportador:
    """La última ejecución COMPLETADA del importador (#232), leída de `ImportRun`.

    No es la comprobación de #231: esta describe el ciclo (descargas, importados, ausentes…) y
    aquella la observación de las rutas de la biblioteca. `disparador=None` = run antiguo sin dato.
    """
    run_id: str
    started_at: datetime
    finished_at: datetime | None
    disparador: str | None
    files_scanned: int
    imported_count: int
    duplicate_count: int
    unsorted_count: int
    error_count: int
    disappeared_count: int
    reappeared_count: int
    errors: list[str]

    @property
    def duracion_segundos(self) -> float | None:
        if self.finished_at is None:
            return None
        return max(0.0, (self.finished_at - self.started_at).total_seconds())

    @property
    def con_cambios(self) -> bool:
        return bool(self.imported_count or self.unsorted_count
                    or self.disappeared_count or self.reappeared_count)


async def ultima_ejecucion_importador(db: AsyncSession, run_id: str | None = None) -> UltimaEjecucionImportador | None:
    """Última ejecución completada (o la de `run_id`), solo de ciclos del importador (`kind` ausente)."""
    consulta = select(ImportRun).where(_ciclos_del_importador())
    if run_id:
        try:
            consulta = consulta.where(ImportRun.id == UUID(run_id))
        except (ValueError, TypeError):
            return None
    run = (await db.execute(
        consulta.order_by(ImportRun.started_at.desc(), ImportRun.id.desc()).limit(1)
    )).scalar_one_or_none()
    if run is None:
        return None
    detalles = dict(run.details or {})
    reappeared = detalles.get("reappeared")
    return UltimaEjecucionImportador(
        run_id=str(run.id), started_at=run.started_at, finished_at=run.finished_at,
        disparador=(detalles.get("disparador") if isinstance(detalles.get("disparador"), str) else None),
        files_scanned=run.files_scanned, imported_count=run.imported_count,
        duplicate_count=run.duplicate_count, unsorted_count=run.unsorted_count,
        error_count=run.error_count, disappeared_count=run.disappeared_count,
        reappeared_count=len(reappeared) if isinstance(reappeared, list) else 0,
        errors=list(detalles.get("errors") or []),
    )


# Orden de la lista (decisión del PO, 2026-10-27): `missing_since` con lo más reciente primero; los que no tienen
# fecha, al final; desempate por nombre y por id. Paginación por CURSOR sobre esa misma clave: si entre dos peticiones
# aparece o desaparece algún archivo, no se repite ni se salta ninguno de los que quedan «por delante».
def _codificar(sin_fecha: bool, desde: datetime | None, nombre: str, id_: UUID) -> str:
    crudo = json.dumps([sin_fecha, desde.isoformat() if desde else None, nombre, str(id_)])
    return base64.urlsafe_b64encode(crudo.encode()).decode().rstrip("=")


def _decodificar(token: str) -> tuple[bool, datetime | None, str, UUID] | None:
    try:
        sin_fecha, desde, nombre, id_ = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
        fecha = datetime.fromisoformat(desde) if desde else None
        if not isinstance(sin_fecha, bool) or not isinstance(nombre, str) or (not sin_fecha and fecha is None):
            return None
        return sin_fecha, fecha, nombre, UUID(id_)
    except (binascii.Error, ValueError, TypeError, json.JSONDecodeError):
        return None


def _despues_de(cursor: tuple[bool, datetime | None, str, UUID]):
    sin_fecha, desde, nombre, id_ = cursor
    mismo_nombre_y_despues = or_(File.file_name > nombre, and_(File.file_name == nombre, File.id > id_))
    if sin_fecha:
        return and_(File.missing_since.is_(None), mismo_nombre_y_despues)
    return or_(
        File.missing_since.is_(None),
        File.missing_since < desde,
        and_(File.missing_since == desde, mismo_nombre_y_despues),
    )


async def contar_no_disponibles(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(File).where(File.is_missing.is_(True)))).scalar_one()


async def listar_no_disponibles(db: AsyncSession, despues: str | None = None,
                                limite: int = LIMITE_PAGINA) -> PaginaNoDisponibles:
    """Una página de los archivos con `is_missing`, con su serie y número si siguen vinculados. Tres consultas como
    mucho (total y página); no modifica nada. Un token ilegible se trata como «desde el principio»."""
    total = await contar_no_disponibles(db)
    consulta = (
        select(File.id, File.file_name, File.missing_since, Series.title, Issue.issue_number)
        .outerjoin(Issue, File.issue_id == Issue.id).outerjoin(Series, Issue.series_id == Series.id)
        .where(File.is_missing.is_(True)))
    cursor = _decodificar(despues) if despues else None
    if cursor:
        consulta = consulta.where(_despues_de(cursor))
    filas = (await db.execute(
        consulta.order_by(File.missing_since.is_(None), File.missing_since.desc(), File.file_name, File.id)
        .limit(limite + 1))).all()
    hay_mas = len(filas) > limite
    pagina = filas[:limite]
    archivos = [ArchivoNoDisponible(id=str(f.id), nombre=f.file_name, desde=f.missing_since, serie=f.title,
                                    numero=f.issue_number) for f in pagina]
    siguiente = None
    if hay_mas and pagina:
        ultimo = pagina[-1]
        siguiente = _codificar(ultimo.missing_since is None, ultimo.missing_since, ultimo.file_name, ultimo.id)
    return PaginaNoDisponibles(archivos=archivos, total=total, siguiente=siguiente)
