"""Novedades de editoriales españolas (D5): Norma y Panini, sin ECC.

Solo se leen páginas públicas que su `robots.txt` permite. ECC devuelve hoy
`User-agent: * / Disallow: *` en `ecccomics.com`, así que no se consulta: no se
salta el robots para «completar» la vista. Norma se lee de `/cuando-sale/…`
(no de `/novedades/`, que está deshabilitado para todos en su robots). Panini
se lee de la categoría pública de cómics, que ordena por fecha de lanzamiento.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from html import unescape
from urllib.parse import urljoin

import httpx
import structlog

from zascarr.database import async_session_factory
from zascarr.utils.cache_http import CacheHttp, PoliticaCacheDominio, pedir_con_cache
from zascarr.utils.cortesia import PoliticaFuente, cortesia_de_proceso
from zascarr.utils.robots import gestor_robots_de_proceso

logger = structlog.get_logger()

NORMA_BASE = "https://www.normaeditorial.com"
NORMA_RUTAS = (
    "/cuando-sale/comic-americano",
    "/cuando-sale/comic-europeo",
    "/cuando-sale/manga",
)
PANINI_URL = "https://www.panini.es/shp_esp_es/comics.html"

_MESES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre")
_RE_FECHA_NORMA = re.compile(
    r"A\s+LA\s+VENTA\s+EL\s+(\d{1,2})\s+DE\s+(" + "|".join(_MESES) + ")",
    re.IGNORECASE)
_RE_ITEM_NORMA = re.compile(r'<div class="item">(.*?)</div>\s*(?=<div class="item">|</section>)',
                            re.IGNORECASE | re.DOTALL)
_RE_LI = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_RE_TAGS = re.compile(r"<[^>]+>")
_RE_PANINI_PRODUCTO = re.compile(
    r'<li class="item product product-item">(.*?)(?=<li class="item product product-item">|</ol>)',
    re.IGNORECASE | re.DOTALL)
_RE_PANINI_FECHA = re.compile(
    r'product-item-attribute-release-date.*?<small>\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*</small>',
    re.IGNORECASE | re.DOTALL)
_RE_PANINI_TITULO = re.compile(
    r'<h3 class="product name product-item-name">.*?'
    r'<a class="product-item-link"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
_RE_PANINI_HREF = re.compile(
    r'href="([^"]+/shp_esp_es/[^"]+\.html)"', re.IGNORECASE)
_RE_ESPACIOS = re.compile(r"\s+")
_CACHE: dict[date, tuple[float, ResultadoES]] = {}
_TTL_S = 30 * 60
#: Los cuerpos de estas páginas son HTML público; 6 h basta y no se revalida cada visita.
POLITICA_CACHE_ES = PoliticaCacheDominio(
    ttl_positivo=timedelta(hours=6),
    margen_retencion_304=timedelta(days=1),
    ttl_negativo=timedelta(hours=6),
    codigos_negativos=frozenset({403, 404, 410}),
)


@dataclass(frozen=True)
class ResultadoES:
    filas: list[NovedadES] = field(default_factory=list)
    fallos: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NovedadES:
    fuente: str
    titulo: str
    fecha: date
    url: str
    editorial: str


def _texto(html: str) -> str:
    return _RE_ESPACIOS.sub(" ", unescape(_RE_TAGS.sub(" ", html))).strip()


def _fecha_norma(mes: str, dia: int, hoy: date) -> date:
    anio = hoy.year
    try:
        fecha = date(anio, _MESES.index(mes.lower()) + 1, dia)
    except ValueError:
        return hoy
    # «cuando-sale» puede listar diciembre en enero: si la fecha queda muy
    # atrás, es del año siguiente, no una novedad pasada.
    if (hoy - fecha).days > 180:
        try:
            fecha = date(anio + 1, fecha.month, fecha.day)
        except ValueError:
            return hoy
    return fecha


def parsear_norma(html: str, *, hoy: date, url: str = NORMA_BASE) -> list[NovedadES]:
    out: list[NovedadES] = []
    for bloque in _RE_ITEM_NORMA.findall(html):
        m = _RE_FECHA_NORMA.search(_texto(bloque))
        if not m:
            continue
        fecha = _fecha_norma(m.group(2), int(m.group(1)), hoy)
        for li in _RE_LI.findall(bloque):
            titulo = _texto(li)
            if titulo and len(titulo) < 300:
                out.append(NovedadES(
                    fuente="Norma", titulo=titulo, fecha=fecha,
                    url=urljoin(url, "/cuando-sale/"), editorial="Norma Editorial"))
    return out


def parsear_panini(html: str, *, hoy: date) -> list[NovedadES]:
    out: list[NovedadES] = []
    for bloque in _RE_PANINI_PRODUCTO.findall(html):
        mf = _RE_PANINI_FECHA.search(bloque)
        mt = _RE_PANINI_TITULO.search(bloque)
        mh = _RE_PANINI_HREF.search(bloque)
        if not (mf and mt):
            continue
        dia, mes, anio = (int(x) for x in mf.groups())
        if anio < 100:
            anio += 2000
        try:
            fecha = date(anio, mes, dia)
        except ValueError:
            continue
        titulo = _texto(mt.group(1))
        if not titulo:
            continue
        out.append(NovedadES(
            fuente="Panini", titulo=titulo, fecha=fecha,
            url=urljoin(PANINI_URL, mh.group(1)) if mh else PANINI_URL,
            editorial="Panini Comics"))
    return out


async def _pedir(url: str, *, cache, robots) -> str:
    politica = PoliticaFuente("editorial", "Editorial", 2.5, max_intentos=1,
                              max_redirecciones=3)
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=False,
                                 headers={"User-Agent": "ZascArr/0.1"}) as cliente:
        respuesta = await pedir_con_cache(
            cliente, "GET", url, politica=politica,
            politica_cache=POLITICA_CACHE_ES, cache=cache, robots=robots,
            espera_max_s=30.0, cortesia=cortesia_de_proceso(),
            permitir_apagada=True)
        return respuesta.text


async def cargar_norma(hoy: date | None = None, *, cache=None, robots=None) -> ResultadoES:
    hoy = hoy or date.today()
    cache = cache or CacheHttp(async_session_factory)
    robots = robots or gestor_robots_de_proceso()
    out: list[NovedadES] = []
    fallos: set[str] = set()
    for ruta in NORMA_RUTAS:
        try:
            html = await _pedir(NORMA_BASE + ruta, cache=cache, robots=robots)
            out.extend(parsear_norma(html, hoy=hoy, url=NORMA_BASE + ruta))
        except Exception as exc:  # noqa: BLE001 — una ruta caída no tumba la vista
            logger.warning("novedades_es.norma_fallida", error=type(exc).__name__)
            fallos.add("Norma")
    return ResultadoES(filas=out, fallos=sorted(fallos))


async def cargar_panini(hoy: date | None = None, *, cache=None, robots=None) -> ResultadoES:
    hoy = hoy or date.today()
    cache = cache or CacheHttp(async_session_factory)
    robots = robots or gestor_robots_de_proceso()
    try:
        html = await _pedir(PANINI_URL, cache=cache, robots=robots)
        return ResultadoES(filas=parsear_panini(html, hoy=hoy))
    except Exception as exc:  # noqa: BLE001
        logger.warning("novedades_es.panini_fallida", error=type(exc).__name__)
        return ResultadoES(fallos=["Panini"])


async def cargar_novedades_es(hoy: date | None = None, *, cache=None,
                              robots=None) -> ResultadoES:
    """Norma y Panini. ECC no se consulta: su robots.txt prohíbe todo."""
    hoy = hoy or date.today()
    guardado = _CACHE.get(hoy)
    if guardado is not None and time.monotonic() - guardado[0] < _TTL_S:
        return guardado[1]
    try:
        norma = await cargar_norma(hoy, cache=cache, robots=robots)
    except Exception as exc:  # noqa: BLE001
        logger.warning("novedades_es.norma_fallida", error=type(exc).__name__)
        norma = ResultadoES(fallos=["Norma"])
    try:
        panini = await cargar_panini(hoy, cache=cache, robots=robots)
    except Exception as exc:  # noqa: BLE001
        logger.warning("novedades_es.panini_fallida", error=type(exc).__name__)
        panini = ResultadoES(fallos=["Panini"])
    resultado = ResultadoES(filas=[*norma.filas, *panini.filas],
                            fallos=sorted({*norma.fallos, *panini.fallos}))
    _CACHE[hoy] = (time.monotonic(), resultado)
    return resultado


def limpiar_cache() -> None:
    _CACHE.clear()
