"""Piezas comunes de los extractores de guías de lectura (SCR3, entrega 1).

Solo hechos: cada extractor devuelve el **orden**, la **referencia** (serie/número/año tal
como la escribe la guía) y, opcionalmente, la **sección** y la URL del ítem. Nunca la prosa
del autor: las guías declaran `Content-Signal: use=reference` y aquí no hay campo donde
guardarla (solo se enlaza la guía en la entrega 2).

Contrato de red:
- Todo GET pasa por `utils/cache_http.pedir_con_cache` (caché condicional + robots de SCR1)
  con dos políticas: **guía** (14 d fresca, 60 d de revalidación, negativa 24 h) y
  **sitemap** (24 h, 14 d, negativa 6 h). UA identificado y sin `bypass_cache`.
- Fuente apagada / sin turno / negativa / robots ⇒ `None` o `[]` con log estructurado (sin
  URL ni prosa), nunca una excepción al orquestador.
- Tope de cuerpo `MAX_CUERPO = 2 MiB` (alineado con la caché) y parseo en `asyncio.to_thread`.
- Las fuentes se estrenan **apagadas**: el encendido en `config.py`/Ajustes y las filas de
  `LEGAL.md` son la integración de fuentes de la spec §5, fuera de esta entrega. Mientras no
  exista el flag, `fuente_habilitada()` las considera apagadas y el extractor devuelve vacío.
"""
from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta
from urllib.parse import urljoin, urlsplit

import httpx
import structlog
from lxml import etree

from zascarr.config import get_settings
from zascarr.utils.cache_http import (
    CacheHttpProtocolo,
    PoliticaCacheDominio,
    pedir_con_cache,
)
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    FuenteApagada,
    politica_de,
)
from zascarr.utils.peticiones import ErrorDePeticion, ReintentosAgotados, RespuestaNoTransitoria
from zascarr.utils.robots import (
    USER_AGENT,
    AccesoProhibidoPorRobots,
    GestorRobots,
    gestor_robots_de_proceso,
)

logger = structlog.get_logger()

#: Tope de cuerpo de una guía o un sitemap: lo mismo que persiste la caché de SCR1 (2 MiB).
MAX_CUERPO = 2 * 1024 * 1024
#: Alias con los nombres de la spec §2 (`MAX_CUERPO_HTML = MAX_CUERPO_SITEMAP = 2 MiB`).
MAX_CUERPO_HTML = MAX_CUERPO
MAX_CUERPO_SITEMAP = MAX_CUERPO
#: Topes de la spec §2: no se procesan sitemaps gigantes ni se aceptan más guías que estas.
MAX_LOCS = 10_000
MAX_GUIAS = 2_000
#: Cotas de campos (SecOps m-5): lo que se acepta de una guía externa y se persiste/muestra.
MAX_REFERENCIA = 2_000            # = MAX_REFERENCIA del resolver
MAX_SECCION = 200
MAX_TITULO_GUIA = 500             # = StoryArc.title / Series.title (String(500))
MAX_URL_ITEM = 500
#: Extensiones que no son guías (imágenes, estáticos): defensa común para las dos fuentes.
_RE_RECURSO = re.compile(
    r"\.(?:jpe?g|png|gif|webp|avif|svg|ico|css|js|json|xml|pdf|zip|txt|woff2?)$",
    re.IGNORECASE)

#: Caché de una guía: 14 días fresca, +60 de revalidación (la matriz del estudio §5.3).
POLITICA_CACHE_GUIA = PoliticaCacheDominio(
    ttl_positivo=timedelta(days=14),
    margen_retencion_304=timedelta(days=60),
    ttl_negativo=timedelta(hours=24),
    codigos_negativos=frozenset({404, 410}),
)
#: Caché de un sitemap: 24 h fresca, +14 de revalidación, negativa 6 h.
POLITICA_CACHE_SITEMAP = PoliticaCacheDominio(
    ttl_positivo=timedelta(hours=24),
    margen_retencion_304=timedelta(days=14),
    ttl_negativo=timedelta(hours=6),
    codigos_negativos=frozenset({404, 410}),
)

def politica_de_sitio(sitio: str, ajustes=None):
    """`PoliticaFuente` del sitio desde `config.py`/`cortesia.py` (única fuente de verdad)."""
    return politica_de(sitio, ajustes if ajustes is not None else get_settings())


def url_de_sitio_valida(url: str, hosts_permitidos: tuple[str, ...], *,
                        rutas_prohibidas: tuple[str, ...] = (),
                        exigir_pagina: bool = False) -> bool:
    """Validación común de una URL de guía (SecOps m-3), antes de pedir nada.

    Solo `https`, host de la allowlist, **sin userinfo**, puerto 443/por defecto, **sin
    query**, sin `..` ni caracteres de control, sin extensión de recurso y (si `exigir_pagina`)
    con una ruta de página (no la raíz). Rechaza también las rutas prohibidas del sitio.
    """
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        return False
    if partes.scheme != "https" or (partes.hostname or "").lower() not in hosts_permitidos:
        return False
    if partes.username is not None or partes.password is not None or "@" in partes.netloc:
        return False
    if puerto not in (None, 443):
        return False
    if partes.query:
        return False
    ruta = partes.path
    if not ruta.startswith("/") or ".." in ruta or any(ord(c) < 32 for c in ruta):
        return False
    minuscula = ruta.lower()
    if any(minuscula.startswith(prohibida) for prohibida in rutas_prohibidas):
        return False
    if _RE_RECURSO.search(ruta):
        return False
    if exigir_pagina:
        return ruta != "/" and bool(re.fullmatch(r"/[A-Za-z0-9][A-Za-z0-9._~/-]*", ruta))
    return True


def url_de_item(base: str, href: str | None) -> str | None:
    """Enlace «Read» de un ítem: solo http(s), sin credenciales y acotado (SecOps m-2)."""
    if not href or not href.strip():
        return None
    try:
        absoluta = urljoin(base, href.strip())
        partes = urlsplit(absoluta)
        puerto = partes.port
    except ValueError:
        return None
    if partes.scheme not in ("http", "https") or not partes.hostname:
        return None
    if partes.username is not None or partes.password is not None:
        return None
    if puerto not in (None, 80, 443):
        return None
    if len(absoluta) > MAX_URL_ITEM:
        return None
    return absoluta


def entrada_de_guia(orden: int, referencia: str, seccion: str | None,
                    href: str | None, base_url: str) -> RawReadingEntry | None:
    """Construye una entrada ya saneada (cotas + enlace http(s)) o `None` si no vale."""
    texto = " ".join(referencia.split())
    if not texto or len(texto) > MAX_REFERENCIA:
        return None
    seccion_limpia = None
    if seccion:
        seccion_limpia = " ".join(seccion.split())[:MAX_SECCION] or None
    return RawReadingEntry(orden=orden, referencia=texto, seccion=seccion_limpia,
                           item_url=url_de_item(base_url, href))


def _texto(elementos) -> str | None:
    """Primer texto no vacío de una lista de nodos lxml (o de cadenas), con espacios limpios."""
    for elemento in elementos:
        bruto = elemento.text_content() if hasattr(elemento, "text_content") else str(elemento)
        texto = " ".join(bruto.split())
        if texto:
            return texto
    return None


@dataclass(frozen=True, slots=True)
class GuiaResumen:
    """Una guía descubierta en el sitemap. Solo hechos: sitio, URL y fecha si consta."""

    sitio: str
    url: str
    actualizada: str | None = None


@dataclass(frozen=True, slots=True)
class RawReadingEntry:
    """Un ítem de una guía en orden de lectura. No hay campo para prosa a propósito."""

    orden: int
    referencia: str
    seccion: str | None
    item_url: str | None


@dataclass(frozen=True, slots=True)
class GuiaLeida:
    """Guía leída: título de la página y entradas en orden DOM (1..N)."""

    sitio: str
    url: str
    titulo: str | None
    entradas: tuple[RawReadingEntry, ...]


def parsear_sitemap(contenido: bytes, filtro: Callable[[str], bool],
                    sitio: str = "") -> list[GuiaResumen]:
    """URLs de guía de un `urlset`, filtradas y sin repetir, con su `lastmod` si consta.

    Pura y lineal sobre el XML (parser sin red ni entidades externas). Tolera namespaces y
    sitemaps con `<url>` o con `<loc>` sueltos.
    """
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)
    try:
        raiz = etree.fromstring(contenido, parser=parser)
    except (etree.XMLSyntaxError, ValueError):
        return []                        # m-4: XML vacío/roto ⇒ [], nunca excepción
    if raiz is None:
        return []
    guias: list[GuiaResumen] = []
    vistos: set[str] = set()
    leidos = 0
    for nodo in raiz.xpath("//*[local-name()='url']"):
        if leidos >= MAX_LOCS:
            break
        loc = _texto(nodo.xpath("./*[local-name()='loc']/text()"))
        if loc is None:
            continue
        leidos += 1
        if loc in vistos or not filtro(loc):
            continue
        vistos.add(loc)
        guias.append(GuiaResumen(sitio=sitio, url=loc,
                                 actualizada=_texto(nodo.xpath(
                                     "./*[local-name()='lastmod']/text()"))))
        if len(guias) >= MAX_GUIAS:
            break
    if guias:
        return guias
    # Respaldo: sitemaps que no envuelven cada loc en <url> (solo tienen <loc> sueltos).
    for loc in raiz.xpath("//*[local-name()='loc']/text()"):
        if leidos >= MAX_LOCS:
            break
        leidos += 1
        loc = " ".join(str(loc).split())
        if not loc or loc in vistos or not filtro(loc):
            continue
        vistos.add(loc)
        guias.append(GuiaResumen(sitio=sitio, url=loc))
        if len(guias) >= MAX_GUIAS:
            break
    return guias


class ExtractorGuias:
    """Base de los dos adaptadores: sitemap, descarga cacheada y parseo en hilo aparte."""

    sitio: str = ""
    hosts_permitidos: tuple[str, ...] = ()

    def __init__(
        self,
        cache: CacheHttpProtocolo,
        *,
        robots: GestorRobots | None = None,
        transporte: httpx.AsyncBaseTransport | None = None,
        cortesia=None,
        reloj=time.monotonic,
        dormir=asyncio.sleep,
        espera_max_s: float = 30.0,
    ):
        self._cache = cache
        self._robots = robots if robots is not None else gestor_robots_de_proceso()
        self._transporte = transporte
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ExtractorGuias:
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── red ─────────────────────────────────────────────────────────────────────────────────
    @property
    def sitemap_url(self) -> str:
        raise NotImplementedError

    def _cliente(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._transporte, timeout=25.0, follow_redirects=False,
                headers={"User-Agent": USER_AGENT},
            )
        return self._client

    async def _descargar(self, url: str,
                         politica_cache: PoliticaCacheDominio) -> httpx.Response | None:
        """GET por la caché/robots de SCR1; cualquier fallo esperable es `None` + log."""
        try:
            respuesta = await pedir_con_cache(
                self._cliente(), "GET", url,
                politica=politica_de_sitio(self.sitio),
                politica_cache=politica_cache,
                cache=self._cache,
                robots=self._robots,
                espera_max_s=self._espera_max_s,
                cortesia=self._cortesia,
                reloj=self._reloj, dormir=self._dormir,
            )
        except (FuenteApagada, CortesiaEnEspera, AccesoProhibidoPorRobots) as exc:
            logger.info("reading_orders.sin_turno", sitio=self.sitio,
                        motivo=getattr(exc, "motivo", "apagada"))
            return None
        except ErrorDePeticion as exc:
            logger.info("reading_orders.negativa", sitio=self.sitio,
                        codigo=_codigo_de_error(exc))
            return None
        if len(respuesta.content) > MAX_CUERPO:
            logger.warning("reading_orders.cuerpo_demasiado_grande", sitio=self.sitio,
                           bytes=len(respuesta.content), limite=MAX_CUERPO)
            return None
        return respuesta

    # ── API pública ─────────────────────────────────────────────────────────────────────────
    async def descubrir_guias(self) -> list[GuiaResumen]:
        """Guías del sitemap del sitio (una vez, con la caché de 24 h)."""
        respuesta = await self._descargar(self.sitemap_url, POLITICA_CACHE_SITEMAP)
        if respuesta is None:
            return []
        try:
            return await asyncio.to_thread(parsear_sitemap, respuesta.content,
                                           self._filtrar_sitemap, self.sitio)
        except Exception:
            logger.warning("reading_orders.parse_fallido", sitio=self.sitio,
                           motivo="sitemap")
            return []

    async def leer_guia(self, url: str) -> GuiaLeida | None:
        """Lee una guía del sitio; URL validada antes de pedir. Fallo esperable ⇒ `None`."""
        if not self._url_del_sitio(url):
            logger.info("reading_orders.url_rechazada", sitio=self.sitio)
            return None
        respuesta = await self._descargar(url, POLITICA_CACHE_GUIA)
        if respuesta is None:
            return None
        try:
            guia = await asyncio.to_thread(self._parsear, respuesta.content, url)
        except Exception:
            logger.warning("reading_orders.parse_fallido", sitio=self.sitio, motivo="html")
            return None
        if guia is None:
            logger.warning("reading_orders.parse_fallido", sitio=self.sitio,
                           motivo="sin_entradas")
            return None
        # m-5: cotas de campos + renumerado contiguo 1..N (orden de lectura).
        validas = [entrada for entrada in guia.entradas
                   if entrada.referencia and len(entrada.referencia) <= MAX_REFERENCIA]
        entradas = tuple(replace(entrada, orden=indice + 1)
                         for indice, entrada in enumerate(validas))
        titulo = (guia.titulo or "").strip()[:MAX_TITULO_GUIA] or None
        guia = replace(guia, titulo=titulo, entradas=entradas)
        if not guia.entradas:
            logger.warning("reading_orders.parse_fallido", sitio=self.sitio,
                           motivo="sin_entradas")
            return None
        return guia

    # ── lo que implementa cada adaptador ────────────────────────────────────────────────────
    def _url_del_sitio(self, url: str) -> bool:
        """¿Es una URL legítima de este sitio para `leer_guia`? (host/scheme/rutas prohibidas)."""
        raise NotImplementedError

    def _filtrar_sitemap(self, url: str) -> bool:
        """¿Esta `loc` del sitemap es una guía? Por defecto, la misma validación del sitio."""
        return self._url_del_sitio(url)

    def _parsear(self, contenido: bytes, url: str) -> GuiaLeida | None:
        raise NotImplementedError


def _codigo_de_error(exc: ErrorDePeticion) -> int | None:
    """Código HTTP del error, si lo lleva (nunca la URL ni el texto de la fuente)."""
    if isinstance(exc, RespuestaNoTransitoria):
        return exc.codigo
    if isinstance(exc, ReintentosAgotados):
        return exc.ultimo_codigo
    return None


__all__ = [
    "MAX_CUERPO",
    "MAX_CUERPO_HTML",
    "MAX_CUERPO_SITEMAP",
    "MAX_GUIAS",
    "MAX_LOCS",
    "MAX_REFERENCIA",
    "MAX_SECCION",
    "MAX_TITULO_GUIA",
    "MAX_URL_ITEM",
    "POLITICA_CACHE_GUIA",
    "POLITICA_CACHE_SITEMAP",
    "ExtractorGuias",
    "GuiaLeida",
    "GuiaResumen",
    "RawReadingEntry",
    "entrada_de_guia",
    "parsear_sitemap",
    "politica_de_sitio",
    "url_de_item",
    "url_de_sitio_valida",
]
