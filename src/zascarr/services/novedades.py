"""Novedades semanales de cómic USA (D5, primera entrega).

Lee de Comic Vine los números con `cover_date` en la semana y los cruza con las
series seguidas (deseos activos o política de búsqueda distinta de «ninguno»).
No escribe en la base: la vista se calcula a demanda y se cachea en memoria unos
minutos. La parte de Norma/ECC/Panini queda fuera hasta verificar su HTML real.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.core.matcher import normalize_title
from zascarr.models import Publisher, Series, Wishlist, WishlistPolicy, WishlistStatus
from zascarr.services.comic_vine import ComicVineClient

logger = structlog.get_logger()

_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_CACHE: dict[date, tuple[float, list[dict[str, Any]]]] = {}
_TTL_S = 30 * 60


class NovedadesApagadaError(RuntimeError):
    """Comic Vine está apagado o sin clave: la vista no inventa novedades."""


class NovedadesError(RuntimeError):
    """No se pudo consultar la fuente; la vista lo dice sin romper la página."""


@dataclass(frozen=True)
class Novedad:
    cv_id: int
    volumen_id: int | None
    serie: str
    numero: str
    fecha: date
    publicado: bool
    editorial: str | None
    url: str | None
    interes: bool
    series_id: UUID | None


@dataclass(frozen=True)
class Semana:
    inicio: date
    fin: date
    novedades: list[Novedad] = field(default_factory=list)

    @property
    def editoriales(self) -> list[str]:
        return sorted({n.editorial for n in self.novedades if n.editorial})

    @property
    def dias(self) -> list[tuple[date, list[Novedad]]]:
        salida: list[tuple[date, list[Novedad]]] = []
        actual = self.inicio
        while actual <= self.fin:
            del_dia = [n for n in self.novedades if n.fecha == actual]
            if del_dia:
                salida.append((actual, del_dia))
            actual += timedelta(days=1)
        return salida

    @property
    def total(self) -> int:
        return len(self.novedades)

    @property
    def interesantes(self) -> int:
        return sum(1 for n in self.novedades if n.interes)


def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def semana_iso(valor: str | None, *, hoy: date | None = None) -> date:
    """Lunes de la semana pedida; sin valor o inválido, la semana de hoy."""
    hoy = hoy or date.today()
    if not valor:
        return lunes_de(hoy)
    try:
        return lunes_de(date.fromisoformat(valor))
    except (TypeError, ValueError):
        return lunes_de(hoy)


def etiqueta_dia(fecha: date) -> str:
    return f"{_DIAS[fecha.weekday()].capitalize()} {fecha.day} de {_MESES[fecha.month - 1]}"


def etiqueta_semana(inicio: date) -> str:
    fin = inicio + timedelta(days=6)
    return (f"del {inicio.day} de {_MESES[inicio.month - 1]} "
            f"al {fin.day} de {_MESES[fin.month - 1]} de {fin.year}")


def _filas_de_series(series: list[Any]) -> tuple[dict[int, Any], dict[str, list[Any]]]:
    por_cv: dict[int, Any] = {}
    por_titulo: dict[str, list[Any]] = {}
    for fila in series:
        if fila.comic_vine_id is not None:
            por_cv.setdefault(int(fila.comic_vine_id), fila)
        norm = normalize_title(fila.title or "")
        if norm:
            por_titulo.setdefault(norm, []).append(fila)
    return por_cv, por_titulo


def construir_semana(
    items: list[dict[str, Any]], *, inicio: date, series: list[Any],
    wishlist_series: set[UUID], hoy: date | None = None,
) -> Semana:
    """Cruce puro entre lo que publica la fuente y la biblioteca local."""
    hoy = hoy or date.today()
    fin = inicio + timedelta(days=6)
    por_cv, por_titulo = _filas_de_series(series)
    novedades: list[Novedad] = []
    for item in items:
        try:
            fecha = date.fromisoformat(str(item.get("cover_date")))
        except (TypeError, ValueError):
            continue
        if not (inicio <= fecha <= fin):
            continue
        volumen = item.get("volume") or {}
        volumen_id = volumen.get("id")
        titulo = str(volumen.get("name") or "").strip()
        numero = str(item.get("issue_number") or "").strip()
        if not titulo or not numero:
            continue
        fila = None
        if isinstance(volumen_id, int):
            fila = por_cv.get(volumen_id)
        if fila is None:
            candidatas = por_titulo.get(normalize_title(titulo), [])
            if len(candidatas) == 1:
                fila = candidatas[0]
        series_id = fila.id if fila is not None else None
        interes = bool(
            fila is not None
            and (fila.id in wishlist_series
                 or getattr(fila, "wishlist_policy", WishlistPolicy.NONE) != WishlistPolicy.NONE)
        )
        novedades.append(Novedad(
            cv_id=int(item.get("id") or 0),
            volumen_id=volumen_id if isinstance(volumen_id, int) else None,
            serie=titulo,
            numero=numero,
            fecha=fecha,
            publicado=fecha <= hoy,
            editorial=getattr(fila, "publisher_name", None) if fila is not None else None,
            url=item.get("site_detail_url"),
            interes=interes,
            series_id=series_id,
        ))
    novedades.sort(key=lambda n: (n.fecha, n.serie.casefold(), n.numero))
    return Semana(inicio=inicio, fin=fin, novedades=novedades)


async def _items_de_la_semana(inicio: date, *, cliente=None) -> list[dict[str, Any]]:
    fin = inicio + timedelta(days=6)
    guardado = _CACHE.get(inicio)
    if guardado is not None and time.monotonic() - guardado[0] < _TTL_S:
        return guardado[1]
    if cliente is None:
        async with ComicVineClient() as cv:
            items = await cv.issues_by_cover_date(inicio.isoformat(), fin.isoformat())
    else:
        items = await cliente.issues_by_cover_date(inicio.isoformat(), fin.isoformat())
    _CACHE[inicio] = (time.monotonic(), items)
    return items


async def cargar_semana(db: AsyncSession, inicio: date, *, cliente=None,
                        hoy: date | None = None) -> Semana:
    """Consulta la fuente y cruza con las series seguidas. Sin escrituras."""
    ajustes = get_settings()
    if not getattr(ajustes, "comicvine_enabled", False):
        raise NovedadesApagadaError("Comic Vine está apagado en Ajustes.")
    if not getattr(ajustes, "comicvine_api_key", ""):
        raise NovedadesApagadaError("Comic Vine no tiene clave de API.")
    try:
        items = await _items_de_la_semana(inicio, cliente=cliente)
    except Exception as exc:  # noqa: BLE001 — la UI decide cómo mostrarlo
        logger.warning("novedades.fuente_fallida", error=type(exc).__name__)
        raise NovedadesError("No se pudo consultar Comic Vine.") from exc
    filas = list((await db.execute(
        select(Series.id, Series.title, Series.comic_vine_id, Series.wishlist_policy,
               Publisher.name.label("publisher_name"))
        .outerjoin(Publisher, Series.publisher_id == Publisher.id)
    )).all())
    wishlist_series = set((await db.execute(
        select(Wishlist.series_id)
        .where(Wishlist.series_id.is_not(None),
               Wishlist.status != WishlistStatus.RETIRADO)
        .distinct()
    )).scalars().all())
    return construir_semana(
        items, inicio=inicio, series=filas, wishlist_series=wishlist_series, hoy=hoy)


def filtrar_editorial(semana: Semana, editorial: str | None) -> Semana:
    if not editorial:
        return semana
    return Semana(inicio=semana.inicio, fin=semana.fin,
                  novedades=[n for n in semana.novedades if n.editorial == editorial])


def limpiar_cache() -> None:
    _CACHE.clear()
