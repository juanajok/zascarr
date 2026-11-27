# ruff: noqa: E501
"""BL-VINC1: vínculos dudosos. Archivos ya vinculados cuyo nombre o carpeta contradicen su serie.

Especificación: `docs/design/especificacion-BL-VINC1.md` (aprobada el 2026-11-27). El sistema informa y la
persona decide: la búsqueda corre en una transacción `READ ONLY` y solo escribe su informe (`ImportRun` con
`details.kind = "vinculos_dudosos"`). Nunca cambia un vínculo.

- Señales del archivo (R2–R5): el matcher de hoy elige otra serie, el año de la carpeta contradice el
  inicio, el volumen contradice el explícito de la serie, otro título en el número. Forman **lotes** por
  (carpeta, serie).
- R4b: una serie sin volumen explícito que mezcla volúmenes. Es una señal de la **serie**: un grupo por
  serie con su desglose; sus archivos son evidencia, no vínculos dudosos sueltos.
- R7: un lote tiene destino solo con una única candidata compatible con todos sus archivos y con
  identidad editorial positiva (título igual y volumen o año explícitos).

Las señales son funciones puras sobre `Archivo` y `Ficha` (R9); la parte asíncrona solo recoge datos.
No abre ningún archivo de la biblioteca: solo nombre y carpetas de la ruta guardada (R1).
"""
from __future__ import annotations

import asyncio
import contextlib
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from uuid import UUID

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.core.cohort import detectar_ordenes_de_lectura
from zascarr.core.matcher import (
    FUZZY_THRESHOLD,
    MatchStatus,
    SeriesMatcher,
    _anio_de_carpeta,
    _volumen_en_carpeta,
)
from zascarr.models import File, ImportRun, Issue, Series
from zascarr.services import tareas
from zascarr.utils.naming import clave_de_coleccion, es_titulo_de_anual

logger = structlog.get_logger()

KIND = "vinculos_dudosos"
ORIGEN_MANUAL = "manual"

#: El volumen en un título o una carpeta («Vol. 3», «Volume 2», «v2», «Tomo 1»).
_VOLUMEN = re.compile(r"\b(?:vol(?:ume|umen)?|v|tomo)\.?\s*(\d+)\b", re.IGNORECASE)
#: Lo mismo, hasta el final: para comparar títulos sin su volumen (R6).
_VOLUMEN_HASTA_EL_FINAL = re.compile(r"\b(?:vol(?:ume|umen)?|v|tomo)\.?\s*\d+\b.*$", re.IGNORECASE)


# ── Datos ──

@dataclass(frozen=True)
class Ficha:
    """Lo que la revisión sabe de una serie."""

    id: str
    titulo: str
    inicio: int | None = None
    volumen: int | None = None
    numeros: frozenset[str] = frozenset()

    @property
    def volumen_explicito(self) -> int | None:
        """`Series.volume` o el del título («Batman Vol 1»). Nunca la mayoría de sus archivos (R4)."""
        if self.volumen is not None:
            return self.volumen
        m = _VOLUMEN.search(self.titulo or "")
        return int(m.group(1)) if m else None

    @property
    def anual(self) -> bool:
        return es_titulo_de_anual(self.titulo)

    @property
    def numeros_normalizados(self) -> frozenset[str]:
        return frozenset(_sin_ceros(n) for n in self.numeros)


@dataclass(frozen=True)
class Archivo:
    """Un archivo vinculado y lo que el matcher de hoy decide sobre su nombre (R1)."""

    id: str
    ruta: str
    serie_id: str
    issue_id: str
    numero: str
    orden: float | None = None
    origen: str | None = None
    p_serie: str | None = None
    p_numero: str | None = None
    p_volumen: int | None = None
    p_anual: bool = False
    elegida: str | None = None                  # serie que elige el matcher (direct/fuzzy)
    candidatas: tuple[str, ...] = ()            # series por encima del umbral, con la elegida
    clave: str = ""                             # clave de colección del nombre (BL-INF11)

    @property
    def _ruta(self) -> PurePosixPath:
        return PurePosixPath(self.ruta)

    @property
    def carpeta(self) -> str:
        return str(self._ruta.parent)

    @property
    def nombre(self) -> str:
        return self._ruta.name

    @property
    def nombre_carpeta(self) -> str:
        return self._ruta.parent.name

    @property
    def anio_carpeta(self) -> int | None:
        return _anio_de_carpeta(self.nombre_carpeta)

    @property
    def volumen_carpeta(self) -> int | None:
        return _volumen_en_carpeta(Path(self.ruta))

    @property
    def numero_del_nombre(self) -> str:
        return _sin_ceros(self.p_numero or self.numero)


@dataclass
class Motivo:
    senal: str          # otra_serie | anio | volumen | otro_titulo
    texto: str


@dataclass
class Marcado:
    archivo_id: str
    issue_id: str
    nombre: str
    numero: str
    orden: float | None
    motivos: list[Motivo]
    serie_mezcla: bool = False


@dataclass
class Lote:
    carpeta: str
    serie_id: str
    serie_titulo: str
    archivos: list[Marcado]
    destino_id: str | None = None
    destino_titulo: str | None = None
    destino_sin_numeros: bool = False

    @property
    def senales(self) -> int:
        """El mayor número de señales del archivo de sus archivos (R7)."""
        return max((len(m.motivos) for m in self.archivos), default=0)


@dataclass
class EvidenciaMezcla:
    archivo_id: str
    issue_id: str
    nombre: str
    numero: str
    volumen: int
    carpeta: str


@dataclass
class SerieMezclada:
    serie_id: str
    titulo: str
    archivos: list[EvidenciaMezcla] = field(default_factory=list)

    @property
    def volumenes(self) -> list[tuple[int, int]]:
        """(volumen, archivos), de menor a mayor volumen."""
        return sorted(Counter(e.volumen for e in self.archivos).items())

    @property
    def desglose(self) -> list[tuple[int, str, int]]:
        """(volumen, carpeta, archivos): una línea por carpeta y volumen."""
        c = Counter((e.volumen, e.carpeta) for e in self.archivos)
        return [(v, carpeta, n) for (v, carpeta), n in sorted(c.items())]

    @property
    def texto_volumenes(self) -> str:
        partes = [f"del vol. {v} ({n})" for v, n in self.volumenes]
        return partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " y " + partes[-1]


@dataclass
class Informe:
    lotes: list[Lote]
    series_mezcladas: list[SerieMezclada]
    revisados: int = 0

    @property
    def archivos_en_lotes(self) -> int:
        return sum(len(lote.archivos) for lote in self.lotes)


# ── Títulos (R6) ──

def _sin_ceros(numero: str | None) -> str:
    n = (numero or "").strip()
    return n.lstrip("0") or ("0" if n else "")


def normalizar(texto: str | None) -> str:
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def base_titulo(texto: str | None) -> str:
    """El título sin el volumen (ni lo que le sigue), los paréntesis ni los corchetes, normalizado."""
    return normalizar(_VOLUMEN_HASTA_EL_FINAL.sub("", texto or ""))


def habla_de(nombre_carpeta: str, titulo: str) -> bool:
    """R6: el título de la carpeta habla de la serie si uno empieza por el otro."""
    bc, bs = base_titulo(nombre_carpeta), base_titulo(titulo)
    return bool(bc and bs and (bc.startswith(bs) or bs.startswith(bc)))


def volumen_declarado(a: Archivo, titulo: str) -> int | None:
    """R4: el volumen del nombre o, si no lo trae, el de la carpeta si la carpeta habla de `titulo`."""
    if a.p_volumen is not None:
        return a.p_volumen
    v = a.volumen_carpeta
    return v if v is not None and habla_de(a.nombre_carpeta, titulo) else None


# ── Señales del archivo (R2–R5) ──

def es_orden_de_lectura(a: Archivo) -> bool:
    """R2: vínculo manual con un número distinto del del nombre (una saga en su orden)."""
    return a.origen == ORIGEN_MANUAL and _sin_ceros(a.p_numero) != _sin_ceros(a.numero)


def _otra_serie(a: Archivo, fichas: dict[str, Ficha]) -> Motivo | None:
    if not a.elegida or a.elegida == a.serie_id or es_orden_de_lectura(a):
        return None
    titulo = fichas[a.elegida].titulo if a.elegida in fichas else "otra serie"
    return Motivo("otra_serie", f"El nombre encaja con «{titulo}»")


def _anio(a: Archivo, serie: Ficha) -> Motivo | None:
    anio = a.anio_carpeta
    if anio is None or serie.inicio is None or abs(anio - serie.inicio) <= 1:
        return None
    if not habla_de(a.nombre_carpeta, serie.titulo):
        return None
    return Motivo("anio", f"La carpeta dice {anio}; la serie empieza en {serie.inicio}")


def _volumen(a: Archivo, serie: Ficha) -> Motivo | None:
    vs = serie.volumen_explicito
    v = volumen_declarado(a, serie.titulo)
    if v is None or vs is None or v == vs:
        return None
    return Motivo("volumen", f"Dice vol. {v}; la serie es vol. {vs}")


def _claves_dominantes(archivos: list[Archivo]) -> dict[str, str | None]:
    """La clave más repetida de cada serie, con mayoría estricta (R5); None si hay empate."""
    por_serie: dict[str, Counter] = defaultdict(Counter)
    for a in archivos:
        if a.clave:
            por_serie[a.serie_id][a.clave] += 1
    salida: dict[str, str | None] = {}
    for sid, c in por_serie.items():
        (dom, n1), *resto = c.most_common(2)
        salida[sid] = dom if not resto or n1 > resto[0][1] else None
    return salida


def _otro_titulo(a: Archivo, claves_del_numero: dict[str, list[tuple[str, str]]],
                 dominantes: dict[str, str | None]) -> Motivo | None:
    if not a.clave:
        return None
    otras = {c for fid, c in claves_del_numero.get(a.issue_id, []) if fid != a.id and c}
    if not otras or len(otras | {a.clave}) <= 1:
        return None
    dom = dominantes.get(a.serie_id)
    if dom is None or a.clave == dom:
        return None
    return Motivo("otro_titulo", f"Comparte el #{a.numero} con tebeos de otro título")


# ── R4b: la serie mezcla volúmenes ──

def _series_mezcladas(archivos: list[Archivo], fichas: dict[str, Ficha]) -> dict[str, SerieMezclada]:
    por_serie: dict[str, list[tuple[Archivo, int]]] = defaultdict(list)
    for a in archivos:
        serie = fichas.get(a.serie_id)
        if serie is None or serie.volumen_explicito is not None:
            continue
        v = volumen_declarado(a, serie.titulo)
        if v is not None:
            por_serie[a.serie_id].append((a, v))
    salida: dict[str, SerieMezclada] = {}
    for sid, declarados in por_serie.items():
        if len({v for _, v in declarados}) < 2:
            continue
        por_numero: dict[str, set[int]] = defaultdict(set)
        for a, v in declarados:
            por_numero[_sin_ceros(a.numero)].add(v)
        repite = any(len(vs) >= 2 for vs in por_numero.values())
        por_carpeta = len({v for a, v in declarados if a.p_volumen is None}) >= 2
        if not (repite or por_carpeta):
            continue
        salida[sid] = SerieMezclada(serie_id=sid, titulo=fichas[sid].titulo, archivos=[
            EvidenciaMezcla(archivo_id=a.id, issue_id=a.issue_id, nombre=a.nombre, numero=a.numero,
                            volumen=v, carpeta=a.carpeta)
            for a, v in sorted(declarados, key=lambda x: (x[1], x[0].orden is None, x[0].orden or 0, x[0].nombre))])
    return salida


# ── R7: destino posible ──

def _compatible(c: Ficha, a: Archivo) -> bool:
    v, cv = volumen_declarado(a, c.titulo), c.volumen_explicito
    if v is not None and cv is not None and v != cv:
        return False
    anio = a.anio_carpeta
    if (c.inicio is not None and anio is not None and habla_de(a.nombre_carpeta, c.titulo)
            and abs(c.inicio - anio) > 1):
        return False
    if c.anual != a.p_anual:
        return False
    return not c.numeros or a.numero_del_nombre in c.numeros_normalizados


def _identidad(c: Ficha, archivos: list[Archivo]) -> bool:
    """Título igual y, además, volumen o año explícitos que coinciden (solo descartar no basta)."""
    base = base_titulo(c.titulo)
    if not base or not all(base in {base_titulo(a.p_serie), base_titulo(a.nombre_carpeta)} for a in archivos):
        return False
    cv = c.volumen_explicito
    if cv is not None:
        vols = [v for a in archivos if (v := volumen_declarado(a, c.titulo)) is not None]
        if vols and all(v == cv for v in vols):
            return True
    if c.inicio is not None:
        anios = [a.anio_carpeta for a in archivos
                 if a.anio_carpeta is not None and habla_de(a.nombre_carpeta, c.titulo)]
        if anios and all(abs(c.inicio - x) <= 1 for x in anios):
            return True
    return False


def _destino(archivos: list[Archivo], serie_id: str, fichas: dict[str, Ficha]) -> Ficha | None:
    comunes: set[str] | None = None
    for a in archivos:
        propias = {x for x in (a.elegida, *a.candidatas) if x}
        comunes = propias if comunes is None else comunes & propias
    validas = [fichas[c] for c in sorted(comunes or set()) if c != serie_id and c in fichas
               and all(_compatible(fichas[c], a) for a in archivos) and _identidad(fichas[c], archivos)]
    return validas[0] if len(validas) == 1 else None


# ── Evaluación ──

def evaluar(archivos: list[Archivo], fichas: dict[str, Ficha]) -> Informe:
    """Señales, lotes, series mezcladas y destino. Pura: no toca la base de datos ni el disco."""
    claves_del_numero: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for a in archivos:
        claves_del_numero[a.issue_id].append((a.id, a.clave))
    dominantes = _claves_dominantes(archivos)
    mezcladas = _series_mezcladas(archivos, fichas)

    por_lote: dict[tuple[str, str], list[tuple[Archivo, list[Motivo]]]] = defaultdict(list)
    for a in archivos:
        serie = fichas.get(a.serie_id)
        if serie is None:
            continue
        motivos = [m for m in (_otra_serie(a, fichas), _anio(a, serie), _volumen(a, serie),
                               _otro_titulo(a, claves_del_numero, dominantes)) if m is not None]
        if motivos:
            por_lote[(a.carpeta, a.serie_id)].append((a, motivos))

    evidencia = {e.archivo_id for s in mezcladas.values() for e in s.archivos}
    lotes: list[Lote] = []
    for (carpeta, sid), filas in por_lote.items():
        filas.sort(key=lambda x: (x[0].orden is None, x[0].orden or 0, x[0].nombre))
        destino = _destino([a for a, _ in filas], sid, fichas)
        lotes.append(Lote(
            carpeta=carpeta, serie_id=sid, serie_titulo=fichas[sid].titulo,
            archivos=[Marcado(archivo_id=a.id, issue_id=a.issue_id, nombre=a.nombre, numero=a.numero,
                              orden=a.orden, motivos=m, serie_mezcla=a.id in evidencia) for a, m in filas],
            destino_id=destino.id if destino else None,
            destino_titulo=destino.titulo if destino else None,
            destino_sin_numeros=bool(destino) and not destino.numeros))
    lotes.sort(key=lambda lote: (-lote.senales, -len(lote.archivos), lote.serie_titulo, lote.carpeta))
    series = sorted(mezcladas.values(), key=lambda s: (-len(s.archivos), s.titulo))
    return Informe(lotes=lotes, series_mezcladas=series, revisados=len(archivos))


# ── Informe guardado (R8) ──

def a_detalles(informe: Informe) -> dict:
    return {"kind": KIND, "revisados": informe.revisados,
            "lotes": [asdict(lote) for lote in informe.lotes],
            "series_mezcladas": [asdict(s) for s in informe.series_mezcladas]}


def de_detalles(d: dict) -> Informe:
    lotes = [Lote(**{**lote, "archivos": [Marcado(**{**m, "motivos": [Motivo(**x) for x in m["motivos"]]})
                                          for m in lote["archivos"]]})
             for lote in d.get("lotes", [])]
    series = [SerieMezclada(serie_id=s["serie_id"], titulo=s["titulo"],
                            archivos=[EvidenciaMezcla(**e) for e in s["archivos"]])
              for s in d.get("series_mezcladas", [])]
    return Informe(lotes=lotes, series_mezcladas=series, revisados=d.get("revisados", 0))


def filtrar_vigentes(informe: Informe, actuales: dict[str, str | None]) -> Informe:
    """Quita lo que ya no está vinculado al mismo número que en la búsqueda (R8)."""
    def sigue(archivo_id: str, issue_id: str) -> bool:
        return actuales.get(archivo_id) == issue_id

    lotes = []
    for lote in informe.lotes:
        quedan = [m for m in lote.archivos if sigue(m.archivo_id, m.issue_id)]
        if quedan:
            lote.archivos = quedan
            lotes.append(lote)
    series = []
    for s in informe.series_mezcladas:
        s.archivos = [e for e in s.archivos if sigue(e.archivo_id, e.issue_id)]
        if len({e.volumen for e in s.archivos}) >= 2:
            series.append(s)
    return Informe(lotes=lotes, series_mezcladas=series, revisados=informe.revisados)


async def informe_vigente(db: AsyncSession) -> tuple[Informe, datetime] | None:
    """El último informe, sin los archivos cuyo vínculo cambió desde la búsqueda."""
    run = (await db.execute(
        select(ImportRun)
        .where(ImportRun.details["kind"].astext == KIND)
        .order_by(ImportRun.started_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if run is None:
        return None
    informe = de_detalles(run.details or {})
    ids = {m.archivo_id for lote in informe.lotes for m in lote.archivos}
    ids |= {e.archivo_id for s in informe.series_mezcladas for e in s.archivos}
    actuales: dict[str, str | None] = {}
    if ids:
        filas = (await db.execute(
            select(File.id, File.issue_id).where(File.id.in_([UUID(x) for x in ids])))).all()
        actuales = {str(fid): (str(iid) if iid else None) for fid, iid in filas}
    return filtrar_vigentes(informe, actuales), run.started_at


# ── Recogida (R1): nombre, carpetas y lo que el matcher de hoy decide ──

async def recoger(db: AsyncSession, progreso: Callable[[int, int], None] | None = None
                  ) -> tuple[list[Archivo], dict[str, Ficha]]:
    from zascarr.services.importer import decidir_por_nombre, parsear_nombre

    filas = (await db.execute(
        select(File.id, File.file_path, File.file_name, File.metadata_source, File.issue_id,
               Issue.series_id, Issue.issue_number, Issue.sort_order)
        .outerjoin(Issue, Issue.id == File.issue_id)
        .where(File.is_missing.is_(False))
        .order_by(File.file_path)
    )).all()
    numeros: dict[str, set[str]] = defaultdict(set)
    for sid, numero in (await db.execute(select(Issue.series_id, Issue.issue_number))).all():
        numeros[str(sid)].add(numero)
    fichas = {str(r.id): Ficha(id=str(r.id), titulo=r.title, inicio=r.start_year, volumen=r.volume,
                               numeros=frozenset(numeros.get(str(r.id), ())))
              for r in (await db.execute(select(Series.id, Series.title, Series.start_year, Series.volume))).all()}

    por_carpeta: dict[str, list[str]] = defaultdict(list)
    for f in filas:
        por_carpeta[str(PurePosixPath(f.file_path).parent)].append(f.file_name)
    pistas = {c: detectar_ordenes_de_lectura(nombres) for c, nombres in por_carpeta.items()}

    matcher = SeriesMatcher(db)
    vinculadas = [f for f in filas if f.series_id is not None]
    salida: list[Archivo] = []
    for i, f in enumerate(vinculadas, 1):
        path = Path(f.file_path)
        parsed, _aplicada = parsear_nombre(path, pistas[str(PurePosixPath(f.file_path).parent)].get(f.file_name))
        elegida, candidatas = None, ()
        try:
            r = await decidir_por_nombre(
                matcher, SimpleNamespace(path=path, strong_candidate=False, comic_info=None), parsed)
            if r.status in (MatchStatus.DIRECT, MatchStatus.FUZZY) and r.series_id:
                elegida = str(r.series_id)
            candidatas = tuple(dict.fromkeys(
                [*([elegida] if elegida else []),
                 *(str(h.series_id) for h in r.candidates if h.score >= FUZZY_THRESHOLD)]))
        except Exception as exc:  # noqa: BLE001 — un nombre raro no para la revisión; sin ruta en el log
            logger.warning("vinculos_dudosos.matcher_fallido", error=type(exc).__name__)
        salida.append(Archivo(
            id=str(f.id), ruta=f.file_path, serie_id=str(f.series_id), issue_id=str(f.issue_id),
            numero=f.issue_number, orden=f.sort_order, origen=f.metadata_source,
            p_serie=parsed.series, p_numero=parsed.issue_number, p_volumen=parsed.volume,
            p_anual=bool(parsed.is_annual), elegida=elegida, candidatas=candidatas,
            clave=clave_de_coleccion(f.file_name)))
        if progreso is not None:
            progreso(i, len(vinculadas))
    return salida, fichas


async def buscar(db: AsyncSession, progreso: Callable[[int, int], None] | None = None) -> Informe:
    archivos, fichas = await recoger(db, progreso)
    return evaluar(archivos, fichas)


async def ejecutar(fabrica, progreso: Callable[[int, int], None] | None = None) -> Informe:
    """Busca en una transacción de solo lectura y guarda el informe en otra, corta."""
    inicio = datetime.now(UTC)
    async with fabrica() as s:
        await s.execute(text("SET TRANSACTION READ ONLY"))
        try:
            informe = await buscar(s, progreso)
        finally:
            await s.rollback()
    async with fabrica() as s:
        s.add(ImportRun(started_at=inicio, finished_at=datetime.now(UTC), files_scanned=informe.revisados,
                        details=a_detalles(informe)))
        await s.commit()
    logger.info("vinculos_dudosos.terminado", revisados=informe.revisados,
                lotes=len(informe.lotes), archivos=informe.archivos_en_lotes,
                series_mezcladas=len(informe.series_mezcladas),
                duracion_ms=int((datetime.now(UTC) - inicio).total_seconds() * 1000))
    return informe


# ── Segundo plano: una búsqueda a la vez (R8) ──

class FaseBusqueda(StrEnum):
    INACTIVO = "inactivo"
    CORRIENDO = "corriendo"
    TERMINADO = "terminado"
    ERROR = "error"


@dataclass
class EstadoBusqueda:
    fase: FaseBusqueda = FaseBusqueda.INACTIVO
    iniciado: datetime | None = None
    causa: str | None = None            # solo el tipo de excepción

    @property
    def en_curso(self) -> bool:
        return self.fase is FaseBusqueda.CORRIENDO


_estado = EstadoBusqueda()
_tarea: asyncio.Task | None = None
_tarea_id: str | None = None


def estado_actual() -> EstadoBusqueda:
    return _estado


async def _ejecutar_en_tarea(fabrica) -> None:
    def progreso(hechos: int, total: int) -> None:
        if _tarea_id is not None:
            tareas.actualizar(_tarea_id, hechos=hechos, total=total, fase="Revisando")
    await ejecutar(fabrica, progreso)


async def _correr(fabrica) -> None:
    global _tarea_id
    tarea = tareas.iniciar("vinculos", enlace="/ui/auditoria#vinculos-dudosos", origen="vinculos")
    _tarea_id = tarea.id if tarea else None
    try:
        await _ejecutar_en_tarea(fabrica)
        _estado.fase = FaseBusqueda.TERMINADO
        if tarea is not None:
            tareas.terminar(tarea.id, resumen="Búsqueda terminada")
    except asyncio.CancelledError:
        _estado.fase = FaseBusqueda.INACTIVO
        if tarea is not None:
            tareas.error(tarea.id, tipo_error="CancelledError")
        raise
    except Exception as exc:  # noqa: BLE001 — el estado no propaga detalle técnico
        _estado.fase = FaseBusqueda.ERROR
        _estado.causa = type(exc).__name__
        if tarea is not None:
            tareas.error(tarea.id, tipo_error=type(exc).__name__)
        logger.warning("vinculos_dudosos.fallido", error=type(exc).__name__)
    finally:
        _tarea_id = None


def iniciar(fabrica) -> bool:
    """Lanza la búsqueda en segundo plano. False si ya había una en curso."""
    global _estado, _tarea
    if _estado.en_curso:
        return False
    _estado = EstadoBusqueda(fase=FaseBusqueda.CORRIENDO, iniciado=datetime.now(UTC))
    _tarea = asyncio.create_task(_correr(fabrica))
    return True


async def detener() -> None:
    global _tarea, _estado
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _tarea
    _tarea = None
    _estado = EstadoBusqueda()


def reiniciar_para_pruebas() -> None:
    global _tarea, _estado, _tarea_id
    if _tarea is not None and not _tarea.done():
        _tarea.cancel()
    _tarea = None
    _tarea_id = None
    _estado = EstadoBusqueda()
