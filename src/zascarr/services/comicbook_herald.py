"""Comic Book Herald por RSS (SCR5): solo el feed público, sin WAF ni HTML de artículos.

Decisión del PO (2026-11-14): la fuente es **el feed RSS 2.0 público** que el sitio ofrece
(`/category/reading-orders/feed/`, verificado en vivo). No se evade ningún WAF ni se piden
artículos, imágenes ni el HTML del tema: de cada `<item>` se leen solo título, enlace, fecha y
categorías. El enlace se guarda para atribuir y abrir el artículo en otra pestaña, nunca se
copia su contenido.

Red (SCR1): todo pasa por `pedir_con_cache` con caché condicional (`http_cache`), robots.txt,
cortesía compartida y el UA del proyecto. TTL del feed: 6 h fresca, retención 2 días para el
304 y negativa de 6 h; ritmo 3,5 s. Tope de cuerpo: 1 MiB. Cualquier fallo esperable devuelve
`[]` con log (la UI simplemente no pinta la sección); `FuenteApagada` y `CortesiaEnEspera` se
propagan para que el llamador omita el ciclo sin tratarlo como error.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
import structlog
from lxml import etree

from zascarr.config import get_settings
from zascarr.database import async_session_factory
from zascarr.utils.cache_http import (
    CacheHttp,
    CacheHttpProtocolo,
    PoliticaCacheDominio,
    pedir_con_cache,
)
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    FuenteApagada,
    politica_de,
)
from zascarr.utils.peticiones import ErrorDePeticion
from zascarr.utils.robots import (
    USER_AGENT,
    AccesoProhibidoPorRobots,
    GestorRobots,
    gestor_robots_de_proceso,
)

logger = structlog.get_logger()

#: Feed por defecto (categoría de guías de lectura; verificado en vivo el 2026-11-14).
FEED_POR_DEFECTO = "https://www.comicbookherald.com/category/reading-orders/feed/"
SITIO = "comic_book_herald"
#: Host canónico del feed; el ápex (`comicbookherald.com`) y otros puertos no se aceptan
#: (SecOps O1: el enlace solo se muestra, pero la validación se mantiene literal).
HOSTS_PERMITIDOS = ("www.comicbookherald.com",)
PUERTO_PERMITIDO = 443
#: TTL 6 h, retención 2 días, negativa 6 h (matriz del estudio §5.3).
POLITICA_CACHE_FEED = PoliticaCacheDominio(
    ttl_positivo=timedelta(hours=6),
    margen_retencion_304=timedelta(days=2),
    ttl_negativo=timedelta(hours=6),
    codigos_negativos=frozenset({404, 410}),
)
#: Tope del cuerpo del feed (1 MiB): un WordPress no necesita más para 10 guías.
MAX_CUERPO = 1024 * 1024
#: Máximo de guías que se aceptan de un feed (el real trae 10).
MAX_ITEMS = 10
#: Tope defensivo del título y de la URL.
MAX_TITULO = 500
MAX_URL = 500
#: Tope de categorías por item y de cada categoría (un feed manipulado no infla la UI).
MAX_CATEGORIAS = 10
MAX_CATEGORIA = 100
@dataclass(frozen=True, slots=True)
class HeraldItem:
    """Una guía del feed: solo metadatos públicos, sin contenido del artículo."""

    titulo: str
    url: str
    publicado: datetime | None
    categorias: tuple[str, ...] = ()


def _sin_control(texto: str) -> bool:
    """Sin caracteres de control (C0 ni DEL): una URL del feed no los necesita."""
    return not any(ord(caracter) < 32 or ord(caracter) == 127 for caracter in texto)


def _url_del_articulo(url: str) -> str | None:
    """URL de artículo válida (https, allowlist, sin credenciales ni control); o None."""
    if not isinstance(url, str) or len(url) > MAX_URL or not _sin_control(url):
        return None
    try:
        partes = urlsplit(url)
        _ = partes.port
    except ValueError:
        return None
    if partes.scheme.lower() != "https" or (partes.hostname or "").lower() not in HOSTS_PERMITIDOS:
        return None
    if partes.port not in (None, PUERTO_PERMITIDO):
        return None
    if partes.username is not None or partes.password is not None or "@" in partes.netloc:
        return None
    return url


def _url_del_feed(url: str) -> str | None:
    """El feed configurado también pasa por la allowlist; si no, no se pide nada."""
    if not isinstance(url, str) or not url.strip():
        return None
    return _url_del_articulo(url.strip())


def _texto_de(elemento, ruta: str) -> str:
    encontrado = elemento.findtext(ruta)
    return " ".join((encontrado or "").split())


def _categorias_de(item) -> tuple[str, ...]:
    """Categorías del `<item>`: máx. 10, ≤100 caracteres y sin caracteres de control."""
    categorias: list[str] = []
    for elemento in item.findall("category"):
        texto = " ".join((elemento.text or "").split())
        if not texto:
            continue
        if any(ord(caracter) < 32 or ord(caracter) == 127 for caracter in texto):
            continue
        categorias.append(texto[:MAX_CATEGORIA])
        if len(categorias) >= MAX_CATEGORIAS:
            break
    return tuple(categorias)


def _fecha(publicado: str) -> datetime | None:
    if not publicado:
        return None
    try:
        fecha = parsedate_to_datetime(publicado)
    except (TypeError, ValueError, OverflowError):
        return None
    if fecha is None:
        return None
    return fecha.astimezone(UTC) if fecha.tzinfo is not None else fecha.replace(tzinfo=UTC)


def parsear_feed(contenido: bytes) -> list[HeraldItem]:
    """RSS 2.0 a `HeraldItem`; XML roto, XXE o sin `<item>` → `[]` (nunca lanza).

    El parser de lxml es seguro: sin resolver entidades, sin red y sin `huge_tree`.
    """
    if not contenido:
        return []
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False,
                             recover=False)
    try:
        raiz = etree.fromstring(contenido, parser=parser)
    except (etree.XMLSyntaxError, ValueError, TypeError):
        return []
    if raiz is None:
        return []
    items: list[HeraldItem] = []
    for item in raiz.iter("item"):
        titulo = _texto_de(item, "title")
        url = _url_del_articulo(_texto_de(item, "link"))
        if not titulo or url is None:
            continue
        categorias = _categorias_de(item)
        items.append(HeraldItem(
            titulo=titulo[:MAX_TITULO],
            url=url,
            publicado=_fecha(_texto_de(item, "pubDate")),
            categorias=categorias,
        ))
        if len(items) >= MAX_ITEMS:
            break
    return items


class ComicBookHeraldClient:
    """Cliente del feed con la caché/robots de SCR1; una sesión HTTP corta por instancia."""

    def __init__(self, cache: CacheHttpProtocolo | None = None, *,
                 robots: GestorRobots | None = None,
                 transporte: httpx.AsyncBaseTransport | None = None,
                 cortesia=None, reloj=time.monotonic, dormir=asyncio.sleep,
                 espera_max_s: float = 30.0, ajustes: Any = None):
        self._cache = cache
        self._robots = robots
        self._transporte = transporte
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._ajustes = ajustes
        self._cliente_http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ComicBookHeraldClient:
        return self

    async def __aexit__(self, *_exc) -> None:
        if self._cliente_http is not None:
            await self._cliente_http.aclose()
            self._cliente_http = None

    def _cliente(self) -> httpx.AsyncClient:
        if self._cliente_http is None:
            self._cliente_http = httpx.AsyncClient(
                transport=self._transporte, timeout=20.0, follow_redirects=False,
                headers={"User-Agent": USER_AGENT})
        return self._cliente_http

    def _robots_actual(self) -> GestorRobots:
        if self._robots is None:
            self._robots = gestor_robots_de_proceso()
        return self._robots

    def _cache_actual(self) -> CacheHttpProtocolo:
        if self._cache is None:
            self._cache = CacheHttp(async_session_factory)
        return self._cache

    def _ajustes_actuales(self):
        return self._ajustes if self._ajustes is not None else get_settings()

    async def novedades(self) -> list[HeraldItem]:
        """Las últimas guías del feed (máx. 10) o `[]` si no se puede leer.

        `FuenteApagada` y `CortesiaEnEspera` se propagan (no son «feed vacío»): el llamador
        omite la sección/ciclo sin registrarlo como fallo.
        """
        ajustes = self._ajustes_actuales()
        feed = _url_del_feed(str(getattr(
            ajustes, "comic_book_herald_feed_url", FEED_POR_DEFECTO) or FEED_POR_DEFECTO))
        if feed is None:
            logger.warning("comicbook_herald.feed_no_valido", sitio=SITIO)
            return []
        try:
            respuesta = await pedir_con_cache(
                self._cliente(), "GET", feed,
                politica=politica_de(SITIO, ajustes),
                politica_cache=POLITICA_CACHE_FEED,
                cache=self._cache_actual(),
                robots=self._robots_actual(),
                espera_max_s=self._espera_max_s,
                cortesia=self._cortesia,
                reloj=self._reloj, dormir=self._dormir,
            )
        except (FuenteApagada, CortesiaEnEspera):
            raise
        except AccesoProhibidoPorRobots as exc:
            logger.info("comicbook_herald.robots", sitio=SITIO,
                        motivo=getattr(exc, "motivo", "robots"))
            return []
        except ErrorDePeticion as exc:
            logger.info("comicbook_herald.negativa", sitio=SITIO,
                        codigo=getattr(exc, "codigo", "red"))
            return []
        except Exception as exc:
            logger.warning("comicbook_herald.fallo", sitio=SITIO, error=type(exc).__name__)
            return []
        if respuesta.status_code != 200:
            return []
        contenido = respuesta.content or b""
        if len(contenido) > MAX_CUERPO:
            logger.warning("comicbook_herald.cuerpo_demasiado_grande", sitio=SITIO,
                           bytes=len(contenido), limite=MAX_CUERPO)
            return []
        items = parsear_feed(contenido)
        if not items:
            logger.info("comicbook_herald.feed_vacio", sitio=SITIO)
        return items


__all__ = [
    "FEED_POR_DEFECTO",
    "HOSTS_PERMITIDOS",
    "MAX_CUERPO",
    "MAX_ITEMS",
    "POLITICA_CACHE_FEED",
    "SITIO",
    "ComicBookHeraldClient",
    "HeraldItem",
    "parsear_feed",
]
