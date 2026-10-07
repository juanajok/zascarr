"""Scraper de foros IPB (plugin genérico; la URL la aporta el usuario). Rate limit: 2s mínimo.

H5 (seguridad): los enlaces a temas salen del HTML del foro, que NO es de fiar, y las cookies
de sesión del foro son credenciales. Por eso la frontera es el **origen del foro** (esquema,
host y puerto de `FORUM_URL`, que elige quien administra la instalación y puede ser de la LAN):

- Un `href` solo se sigue si pertenece a ese origen. Uno absoluto de OTRO origen (o con
  esquema ajeno, credenciales, `//otro-host` o barras invertidas) se descarta; uno absoluto
  del MISMO origen se reduce a ruta y consulta antes de cualquier `urljoin` (los foros IPB
  suelen emitir enlaces absolutos a sus propios temas: rechazarlos todos dejaría la
  integración sin resultados).
- Las redirecciones no se siguen solas: cada salto se resuelve a mano (máximo 3) y se valida
  contra el origen ANTES de pedirlo. Una redirección a otro origen (incluido http -> https)
  corta la petición; quien administra debe poner en `FORUM_URL` el origen canónico.
- Las cookies viajan solo en las peticiones cuyo origen es EXACTAMENTE el del foro, como
  cabecera explícita: nunca en un `dict` de cookies del cliente, que `httpx` envía a todos
  los hosts.
"""
import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin, urlsplit

import httpx
import structlog

logger = structlog.get_logger()

ED2K_PATTERN   = re.compile(r'ed2k://\|file\|[^"<\s]+', re.IGNORECASE)
MAGNET_PATTERN = re.compile(r'magnet:\?xt=urn:[^"<\s]+', re.IGNORECASE)
TOPIC_PATTERN  = re.compile(r'<a[^>]+href=["\']([^"\']*showtopic=\d+)["\'][^>]*>([^<]+)</a>', re.IGNORECASE)

MAX_SALTOS = 3
_PUERTO_POR_DEFECTO = {"http": 80, "https": 443}
_REDIRECCIONES = frozenset({301, 302, 303, 307, 308})

Origen = tuple[str, str, int]


class OrigenNoPermitidoError(ValueError):
    """Un enlace o una redirección sale del origen del foro. El mensaje es un CÓDIGO, sin la URL."""


def origen_de(url: str) -> Origen | None:
    """(esquema, host, puerto) normalizado, o None si no es una URL http(s) con host válida."""
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        return None
    esquema = partes.scheme.lower()
    host = (partes.hostname or "").rstrip(".").lower()
    if esquema not in _PUERTO_POR_DEFECTO or not host:
        return None
    return esquema, host, puerto or _PUERTO_POR_DEFECTO[esquema]


def _host_para_log(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?")[:100]
    except ValueError:
        return "?"


@dataclass
class ForumResult:
    topic_title: str
    topic_url: str
    ed2k_links: list[str] = field(default_factory=list)
    magnet_links: list[str] = field(default_factory=list)


class ForumScraper:
    def __init__(self, base_url: str, rate_limit: float = 2.0,
                 crear_cliente: Callable[[], httpx.AsyncClient] | None = None):
        self._base = base_url.rstrip("/")
        self._origen = origen_de(self._base)
        self._rate_limit = rate_limit
        self._last_req: float = 0
        self._cookies: dict = {}
        # Las pruebas inyectan un cliente con transporte simulado. Sin redirecciones automáticas.
        self._crear_cliente = crear_cliente or (
            lambda: httpx.AsyncClient(timeout=30.0, follow_redirects=False))

    async def login(self, username: str, password: str) -> bool:
        async with self._crear_cliente() as client:
            r = await client.post(f"{self._base}/index.php?act=Login&CODE=01",
                                  data={"UserName": username, "PassWord": password, "CookieDate": "1"})
            for k, v in r.cookies.items():
                self._cookies[k] = v
            self._logged_in = bool(self._cookies) and r.status_code in (200, 301, 302)
            return self._logged_in

    def _cabeceras(self, url: str) -> dict[str, str]:
        """Las cookies SOLO acompañan a una petición del origen exacto del foro."""
        cabeceras = {"User-Agent": "ZascArr/0.1"}
        if self._cookies and self._origen is not None and origen_de(url) == self._origen:
            cabeceras["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        return cabeceras

    def _resolver_enlace(self, href: str) -> str:
        """URL absoluta del enlace, SOLO si es del origen del foro; si no, se lanza el error."""
        if self._origen is None:
            raise OrigenNoPermitidoError("foro_sin_origen")
        if any(c <= " " or c == "\x7f" or c == "\\" for c in href):
            raise OrigenNoPermitidoError("caracteres_no_permitidos")
        try:
            partes = urlsplit(href)
            partes.port  # noqa: B018  (valida el puerto: lanza ValueError si no lo es)
        except ValueError:
            raise OrigenNoPermitidoError("url_mal_formada") from None
        if partes.scheme or partes.netloc:
            # Absoluto, o `//otro-host/...`: solo vale si ES el origen del foro, y se reduce a
            # ruta y consulta ANTES de cualquier `urljoin`.
            if "@" in partes.netloc or partes.username is not None or partes.password is not None:
                raise OrigenNoPermitidoError("credenciales_en_la_url")
            esquema = partes.scheme or self._origen[0]
            if origen_de(f"{esquema}://{partes.netloc}/") != self._origen:
                raise OrigenNoPermitidoError("otro_origen")
            # Una sola barra inicial: con `//…` la ruta se leería como una referencia SIN esquema
            # y `urljoin` la llevaría a otro host (`https://foro//otro.example/x`).
            ruta = "/" + partes.path.lstrip("/")
            href = ruta + (f"?{partes.query}" if partes.query else "")
        try:
            url = urljoin(self._base + "/", href)
        except ValueError:
            # `urljoin` también lanza con ciertos caracteres Unicode: no debe abortar la búsqueda.
            raise OrigenNoPermitidoError("url_mal_formada") from None
        if origen_de(url) != self._origen:
            raise OrigenNoPermitidoError("otro_origen")
        return url

    async def _get(self, url: str) -> str:
        for _ in range(MAX_SALTOS + 1):
            # Defensa en profundidad: ANTES de cada petición (también tras una redirección)
            # el destino debe ser el origen del foro.
            if origen_de(url) != self._origen:
                raise OrigenNoPermitidoError("otro_origen")
            now = asyncio.get_event_loop().time()
            if (elapsed := now - self._last_req) < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)
            async with self._crear_cliente() as client:
                r = await client.get(url, headers=self._cabeceras(url))
            self._last_req = asyncio.get_event_loop().time()
            if r.status_code in _REDIRECCIONES:
                destino = r.headers.get("location") or ""
                if not destino:
                    raise OrigenNoPermitidoError("redireccion_sin_destino")
                try:
                    url = urljoin(url, destino)
                except ValueError:
                    raise OrigenNoPermitidoError("url_mal_formada") from None
                continue
            r.raise_for_status()
            return r.text
        raise OrigenNoPermitidoError("demasiadas_redirecciones")

    async def use_ipb_search(self, query: str) -> list[ForumResult]:
        try:
            html = await self._get(
                f"{self._base}/index.php?act=Search&CODE=01&keywords={quote(query)}&searchin=titles"
            )
        except OrigenNoPermitidoError as exc:
            logger.warning("forum.search_rechazada", motivo=str(exc))
            return []
        except Exception:
            logger.exception("forum.search_failed", query=query)
            return []
        results = []
        for href, title in TOPIC_PATTERN.findall(html)[:10]:
            try:
                url = self._resolver_enlace(href)
            except OrigenNoPermitidoError as exc:
                # Solo el host y un código: el enlace sale de un HTML que no es de fiar.
                logger.warning("forum.enlace_rechazado", host=_host_para_log(href),
                               motivo=str(exc))
                continue
            try:
                topic_html = await self._get(url)
                ed2k    = list(dict.fromkeys(ED2K_PATTERN.findall(topic_html)))
                magnets = list(dict.fromkeys(MAGNET_PATTERN.findall(topic_html)))
                if ed2k or magnets:
                    results.append(ForumResult(title.strip(), url, ed2k, magnets))
            except OrigenNoPermitidoError as exc:
                logger.warning("forum.tema_rechazado", motivo=str(exc))
            except Exception:
                logger.exception("forum.topic_failed", url=url)
        return results
