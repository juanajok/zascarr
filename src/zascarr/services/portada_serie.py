# ruff: noqa: E501
"""BL-INF6 (#592): elegir a mano la portada de la serie entre las disponibles.

El coleccionista decide qué imagen representa la serie. Sin migración, sin red y sin escribir en
la biblioteca:

- **Candidatas** (`candidatas_de_portada`): las portadas de los números que tienen archivo (hasta
  `MAX_CANDIDATAS` por tanda, con «ver más») y la portada externa ya cacheada. La miniatura de un
  número la sirve BL-INF4 (`/previa.jpg`); la externa, su propia ruta de solo lectura.
- **Elección** (`guardar_eleccion`): queda en `Series.metadata_["portada"]` con la forma
  `{"tipo": "archivo"|"externa", "file_id"|"url", "fecha"}` y añade `cover_url` a
  `locked_fields`. Así el enriquecimiento no la pisa y la procedencia la enseña como manual y
  protegida. La caché que sirve la cascada (`covers/v3/<serie>.jpg` para una portada de archivo y
  `covers/externa/<serie>.jpg` para la externa) la regenera quien elige (router `web/series.py`),
  con las utilidades de `utils/cover.py`.

Este módulo NO extrae portadas, no descarga, no escribe en disco y no toca los archivos: solo
consulta la BD, valida la forma de la elección y la guarda en la serie.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.models import File, Issue, Series
from zascarr.services.comic_vine import es_portada_de_relleno
from zascarr.utils.cover import CACHE_VERSION, CARPETA_EXTERNA, puede_tener_portada

#: Clave dentro de `Series.metadata_` (JSONB, sin migración). No cambia el `metadata_source`.
CLAVE = "portada"
TIPO_ARCHIVO = "archivo"
TIPO_EXTERNA = "externa"
#: Cuántas miniaturas de número caben en una tanda del panel («ver más» pide la siguiente).
MAX_CANDIDATAS = 12
#: Archivos que se miran de un número antes de descartarlo (mismo tope que la previa de BL-INF4).
MAX_ARCHIVOS_NUMERO = 3
#: Campo de `locked_fields` que impide que el enriquecimiento sustituya la portada elegida.
CAMPO_PROTEGIDO = "cover_url"


@dataclass(frozen=True)
class Candidata:
    """Una portada que se puede elegir. `miniatura` es la imagen del selector (240 px); `url` solo
    la lleva la externa (la identidad que se valida al elegir)."""
    tipo: str
    origen: str
    miniatura: str
    issue_id: UUID | None = None
    file_id: UUID | None = None
    url: str | None = None
    elegida: bool = False


@dataclass(frozen=True)
class Candidatas:
    """Lo que pinta el panel: la tanda pedida, la externa (solo en la primera) y si hay más."""
    numeros: tuple[Candidata, ...]
    externa: Candidata | None
    hay_mas: bool
    hay_portada_actual: bool


def eleccion_de_portada(series: Series) -> dict | None:
    """La elección guardada, SI su forma es válida; `None` si no hay o no se puede interpretar.

    Tolerante a propósito: un JSONB tocado a mano (o de una versión futura) no rompe la ficha ni la
    cascada de portada; simplemente se ignora y manda la cascada de siempre."""
    if not isinstance(series.metadata_, dict):
        return None
    eleccion = series.metadata_.get(CLAVE)
    if not isinstance(eleccion, dict):
        return None
    fecha = eleccion.get("fecha")
    if not isinstance(fecha, str) or _fecha_valida(fecha) is None:
        return None
    tipo = eleccion.get("tipo")
    if tipo == TIPO_ARCHIVO:
        if not _uuid_valido(eleccion.get("file_id")):
            return None
        return eleccion
    if tipo == TIPO_EXTERNA:
        url = eleccion.get("url")
        if not isinstance(url, str) or not url.strip():
            return None
        return eleccion
    return None


def guardar_eleccion(series: Series, *, tipo: str, file_id: UUID | None = None,
                     url: str | None = None, ahora: datetime | None = None) -> None:
    """Deja la elección en la serie (se persiste con el `commit` de `get_db`).

    Asigna un dict NUEVO en `metadata_` y una lista NUEVA en `locked_fields`: SQLAlchemy no sigue
    las mutaciones internas de un JSONB/ARRAY, y un `append` o un `del` in situ no se guardaría.
    """
    if tipo == TIPO_ARCHIVO and file_id is None:
        raise ValueError("Una portada de archivo necesita su archivo")
    if tipo == TIPO_EXTERNA and not (isinstance(url, str) and url.strip()):
        raise ValueError("Una portada externa necesita su URL")
    if tipo not in (TIPO_ARCHIVO, TIPO_EXTERNA):
        raise ValueError(f"Tipo de portada desconocido: {tipo!r}")
    fecha = (ahora or datetime.now(UTC)).isoformat()
    eleccion: dict = {"tipo": tipo, "fecha": fecha}
    if tipo == TIPO_ARCHIVO:
        eleccion["file_id"] = str(file_id)
    else:
        eleccion["url"] = url
    series.metadata_ = {**(series.metadata_ or {}), CLAVE: eleccion}
    bloqueados = list(series.locked_fields or [])
    if CAMPO_PROTEGIDO not in bloqueados:
        bloqueados.append(CAMPO_PROTEGIDO)
    series.locked_fields = bloqueados


def quitar_eleccion(series: Series) -> bool:
    """Borra la elección guardada y el lock de `cover_url`; la cascada vuelve a decidir.

    Devuelve si había algo que quitar. Asigna un dict y una lista NUEVOS (mutaciones de JSONB/
    ARRAY in situ no se persisten). NO toca la caché: de eso se encarga quien llama, que sabe si la
    `v3` venía de la elección o de antes."""
    if eleccion_de_portada(series) is None:
        return False
    metadata = dict(series.metadata_ or {})
    metadata.pop(CLAVE, None)
    series.metadata_ = metadata
    series.locked_fields = [campo for campo in (series.locked_fields or [])
                            if campo != CAMPO_PROTEGIDO]
    return True


async def candidatas_de_portada(db: AsyncSession, series: Series, *, desde: int = 0,
                                settings=None) -> Candidatas:
    """Las candidatas de una tanda. La externa solo va en la primera (`desde == 0`): es única.

    No genera miniaturas: las pide el navegador, ya dentro del panel abierto y con `loading="lazy"`.
    """
    ajustes = settings or get_settings()
    covers = Path(ajustes.covers_cache_path)
    eleccion = eleccion_de_portada(series)
    numeros, hay_mas = await _numeros_con_archivo(db, series.id, desde=max(0, desde),
                                                  limite=MAX_CANDIDATAS)
    candidatas: list[Candidata] = []
    if numeros:
        archivos = await _primer_archivo_por_numero(db, series.id, [n[0] for n in numeros])
        for issue_id, numero in numeros:
            archivo = archivos.get(issue_id)
            if archivo is None:
                # Todos sus archivos son de un tipo que no puede dar portada: no se ofrece una
                # miniatura que el navegador pediría para recibir un 404.
                continue
            file_id = archivo[0]
            elegida = (eleccion is not None and eleccion.get("tipo") == TIPO_ARCHIVO
                       and str(eleccion.get("file_id")) == str(file_id))
            candidatas.append(Candidata(
                tipo=TIPO_ARCHIVO,
                origen=_origen_del_numero(numero),
                miniatura=f"/ui/series/{series.id}/numero/{issue_id}/previa.jpg",
                issue_id=issue_id, file_id=file_id, elegida=elegida))
    externa = None
    if desde == 0 and await asyncio.to_thread(_externa_cacheada, covers, series) is not None:
        externa = Candidata(
            tipo=TIPO_EXTERNA,
            origen="",
            miniatura=f"/ui/series/{series.id}/portada/externa.jpg",
            url=series.cover_url,
            elegida=eleccion is not None and eleccion.get("tipo") == TIPO_EXTERNA)
    return Candidatas(
        numeros=tuple(candidatas), externa=externa, hay_mas=hay_mas,
        # El `stat` de la caché en disco va a un hilo (CLAUDE.md §4): el bucle no se bloquea.
        hay_portada_actual=await asyncio.to_thread(
            _hay_portada_actual, series, covers, bool(numeros)))


def _origen_del_numero(numero: str | None) -> str:
    limpio = (numero or "").strip()
    if not limpio:
        return "Del archivo de un número sin número"
    return f"Del archivo del nº {limpio}"


def _fecha_valida(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        return None


def _uuid_valido(valor: object) -> bool:
    try:
        UUID(str(valor))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _externa_cacheada(covers: Path, series: Series) -> Path | None:
    """La portada externa ya cacheada y usable como candidata: existe, `cover_url` la identifica y
    no es la imagen de relleno de Comic Vine (#311). Solo hace `stat` (nada de red ni de discos
    ajenos)."""
    if not series.cover_url or es_portada_de_relleno(series.cover_url):
        return None
    ruta = covers / CARPETA_EXTERNA / f"{series.id}.jpg"
    return ruta if ruta.is_file() else None


def _hay_portada_actual(series: Series, covers: Path, hay_numeros: bool) -> bool:
    """¿Se puede enseñar hoy una portada de esta serie? Basta con que la cascada tenga de dónde:
    una caché ya escrita o, si no, un archivo de número o una externa por descargar."""
    if (covers / CACHE_VERSION / f"{series.id}.jpg").is_file():
        return True
    if (covers / CARPETA_EXTERNA / f"{series.id}.jpg").is_file():
        return True
    if (covers / f"{series.id}.jpg").is_file():
        return True
    if eleccion_de_portada(series) is not None or hay_numeros:
        return True
    return bool(series.cover_url and not es_portada_de_relleno(series.cover_url))


async def _numeros_con_archivo(db: AsyncSession, series_id: UUID, *, desde: int,
                               limite: int) -> tuple[list[tuple[UUID, str | None]], bool]:
    """`(números con algún archivo no ausente, en orden de lectura, ¿hay más?)`. Una fila por
    número (`DISTINCT`): un número con varias ediciones se ofrece una vez."""
    filas = (await db.execute(
        select(Issue.id, Issue.issue_number, Issue.sort_order)
        .join(File, File.issue_id == Issue.id)
        .where(Issue.series_id == series_id, File.is_missing.is_(False))
        .distinct()
        .order_by(Issue.sort_order.asc().nulls_last(), Issue.id.asc())
        .offset(desde)
        .limit(limite + 1)
    )).all()
    return [(fila[0], fila[1]) for fila in filas[:limite]], len(filas) > limite


async def _primer_archivo_por_numero(db: AsyncSession, series_id: UUID,
                                     issue_ids: list[UUID]) -> dict[UUID, tuple[UUID, str, dict | None]]:
    """El primer archivo no ausente de cada número que pueda dar portada (por ruta, como BL-INF4)."""
    if not issue_ids:
        return {}
    filas = (await db.execute(
        select(Issue.id, File.id, File.file_path, File.metadata_["formato_contenido"])
        .join(File, File.issue_id == Issue.id)
        .where(Issue.series_id == series_id, Issue.id.in_(issue_ids), File.is_missing.is_(False))
        .order_by(Issue.id.asc(), File.file_path.asc(), File.id.asc())
    )).all()
    primero: dict[UUID, tuple[UUID, str, dict | None]] = {}
    for issue_id, file_id, ruta, formato in filas:
        if issue_id in primero:
            continue
        if puede_tener_portada(ruta, formato):
            primero[issue_id] = (file_id, str(ruta), formato)
    return primero


async def archivos_de_numero(db: AsyncSession, series_id: UUID, issue_id: UUID, *,
                             file_id: UUID | None = None,
                             limite: int = MAX_ARCHIVOS_NUMERO) -> list[tuple[UUID, str, dict | None]]:
    """Los archivos no ausentes de un número de la serie, con el pedido primero y como mucho
    `limite`. `[]` si el número no es de esa serie o no tiene archivos: el router no distingue los
    casos en superficie (mismo mensaje llano)."""
    filas = (await db.execute(
        select(File.id, File.file_path, File.metadata_["formato_contenido"])
        .join(Issue, File.issue_id == Issue.id)
        .where(Issue.series_id == series_id, Issue.id == issue_id, File.is_missing.is_(False))
        .order_by(File.file_path.asc(), File.id.asc())
        .limit(limite)
    )).all()
    archivos = [(fila[0], str(fila[1]), fila[2]) for fila in filas]
    if file_id is not None:
        # El archivo que la persona vio primero; el resto queda de respaldo por si ese no da portada.
        archivos.sort(key=lambda a: a[0] != file_id)
    return archivos


async def archivo_de_portada(db: AsyncSession, series_id: UUID,
                             file_id: UUID) -> list[tuple[UUID, str, dict | None, int | None]]:
    """`(archivo elegido, si sigue siendo de esa serie y no está ausente)`: id, ruta, formato y
    `file_mtime_ns` (NULL si la fila no lo tiene). Lo usa la cascada para materializar la portada
    elegida y para saber si el archivo CAMBIÓ desde la última materialización (la elección es una
    REFERENCIA, no bytes congelados). `[]` si ya no está."""
    filas = (await db.execute(
        select(File.id, File.file_path, File.metadata_["formato_contenido"], File.file_mtime_ns)
        .join(Issue, File.issue_id == Issue.id)
        .where(File.id == file_id, Issue.series_id == series_id, File.is_missing.is_(False))
        .limit(1)
    )).all()
    return [(fila[0], str(fila[1]), fila[2], fila[3]) for fila in filas]
