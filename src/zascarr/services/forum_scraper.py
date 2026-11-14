"""Scraper de foros IPB (plugin genérico; la URL la aporta el usuario).

H5 (seguridad): los enlaces a temas salen del HTML del foro, que NO es de fiar, y las cookies
de sesión del foro son credenciales. Por eso la frontera es el **origen del foro** (esquema,
host y puerto de `FORUM_URL`, que elige quien administra la instalación y puede ser de la LAN):

- Un `href` solo se sigue si pertenece a ese origen. Uno absoluto de OTRO origen (o con
  esquema ajeno, credenciales, `//otro-host` o barras invertidas) se descarta; uno absoluto
  del MISMO origen se reduce a ruta y consulta antes de cualquier `urljoin`.
- Las redirecciones no se siguen solas: cada salto se resuelve a mano (máximo 3) y se valida
  contra el origen ANTES de pedirlo. Una redirección a otro origen (incluido http -> https)
  corta la petición.
- Las cookies viajan solo en las peticiones cuyo origen es EXACTAMENTE el del foro, como
  cabecera explícita: nunca en un `dict` de cookies del cliente.

SCR4 (charset y flood):
- El foro real (IPB) sirve ISO-8859-1 sin `charset` en la cabecera y con `<meta charset>`:
  `detectar_charset()` usa la cabecera, luego la meta de los primeros 4 KiB y, si no hay
  ninguna, cp1252 (NUNCA UTF-8, que rompe tildes). El login y la búsqueda se envían en ese
  charset (`form_charset=`) y la respuesta se decodifica antes de parsear.
- Una página de «Search Flood Control» llega con HTTP 200: `detectar_flood()` la detecta por
  la caja de error de IPB + la frase (inglés/español) y lanza `ForumFloodControl`
  (subclase de `CortesiaEnEspera`, con bloqueo compartido 20–60 s). Nunca se devuelve `[]`.
- Dos ritmos: lectura (login/temas, `forum_rate_limit`) y búsqueda
  (`forum_search_rate_limit`, 25 s). El UA es el del proyecto y los logs no llevan URL ni
  `s=<sesión>`.
"""
from __future__ import annotations

import asyncio
import codecs
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit, urlunsplit

import httpx
import structlog
from lxml import etree
from lxml.html import HTMLParser, document_fromstring

from zascarr.config import get_settings
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    CortesiaProceso,
    FuenteApagada,
    PoliticaFuente,
    cortesia_de_proceso,
    origen_normalizado,
)
from zascarr.utils.peticiones import (
    DemasiadasRedirecciones,
    RedireccionNoPermitida,
    pedir_con_cortesia,
)
from zascarr.utils.robots import USER_AGENT

logger = structlog.get_logger()

ED2K_PATTERN   = re.compile(r'ed2k://\|file\|[^"<\s]+', re.IGNORECASE)
MAGNET_PATTERN = re.compile(r'magnet:\?xt=urn:[^"<\s]+', re.IGNORECASE)
#: `showtopic=N` con lo que IPB añada detrás (`&s=<sesión>`, `&st=…`): si se exige que el número
#: cierre la URL, los temas con sesión en la query no se detectan (visto en la spec, AC de lectura).
TOPIC_PATTERN = re.compile(
    r'<a[^>]+href=["\']([^"\']*showtopic=\d+[^"\']*)["\'][^>]*>([^<]+)</a>', re.IGNORECASE
)

MAX_SALTOS = 3
_PUERTO_POR_DEFECTO = {"http": 80, "https": 443}
#: Bytes que se miran buscando `<meta charset>` (los primeros de la página).
MAX_BYTES_CHARSET = 4096
#: Segundos de espera del flood: recorte a [20, 60] y 30 si la página no dice cuántos.
FLOOD_MIN_S = 20.0
FLOOD_MAX_S = 60.0
FLOOD_POR_DEFECTO_S = 30.0
#: Sufijos de cookie que identifican a un miembro (sesión real, no la visita anónima de IPB).
#: Se compara por sufijo porque IPB permite un prefijo de cookie por foro (`foro_member_id`,
#: `foro_pass_hash` en La Mansión CRG; visto en vivo el 2026-11-14).
_COOKIES_DE_MIEMBRO = (
    "member_id", "pass_hash", "ips4_member_id", "ips4_pass_hash",
)


def es_cookie_de_miembro(nombre: str) -> bool:
    """¿El nombre de cookie identifica a un miembro, con cualquier prefijo del foro?

    IPB permite prefijos arbitrarios por foro: La Mansión CRG usa `foro_nuevo` en unas cookies
    (`foro_nuevomember_id`) y `foro_` en otras (`foro_nuevosession_id`). Por eso se compara el
    **final** del nombre, no `_` + sufijo.
    """
    nombre = (nombre or "").lower()
    return any(nombre.endswith(sufijo) for sufijo in _COOKIES_DE_MIEMBRO)
#: Parámetros de query que son la sesión (no se guardan ni se pintan; m-1/m-2).
_PARAMS_DE_SESION = frozenset({"s", "sid", "session", "session_id", "sess"})
#: Puertos que no se escriben al normalizar una URL para mostrarla.
_PUERTOS_POR_DEFECTO = {"http": 80, "https": 443}

#: La caja de error de IPB que acompaña a sus avisos (flood incluido).
_RE_CAJA_ERROR = re.compile(
    r'(?:id|class)\s*=\s*["\'][^"\']*(?:errorwrap|errorbox)[^"\']*["\']',
    re.IGNORECASE,
)
#: Frases del aviso de saturación (inglés y español, sin distinguir mayúsculas).
_RE_FRASE_FLOOD = re.compile(
    "|".join(re.escape(frase) for frase in (
        "flood control",
        "control de flood",
        "control de saturación",
        "cannot make another search",
        "you can only search",
        "you may only search",
        "no puedes hacer otra búsqueda",
        "no puedes realizar otra búsqueda",
        "solo puedes hacer una búsqueda",
        "solo puedes realizar una búsqueda",
        "inténtalo de nuevo",
        "intentalo de nuevo",
        "try again",
    )),
    re.IGNORECASE,
)
#: «try again in 42 seconds» / «espera 42 segundos» / «inténtalo de nuevo en 42 segundos».
_RE_SEGUNDOS_FLOOD = re.compile(
    r"(?:try again in|espera|int[ée]ntalo de nuevo en)\s+(\d+)\s*(?:seconds|segundos)",
    re.IGNORECASE,
)

Origen = tuple[str, str, int]


class OrigenNoPermitidoError(ValueError):
    """Un enlace o una redirección sale del origen del foro. El mensaje es un CÓDIGO, sin la URL."""


class ForumFloodControl(CortesiaEnEspera):  # noqa: N818 — nombre del contrato (§2)
    """IPB pidió esperar por saturación (HTTP 200). No es «sin resultados» ni un fallo."""

    def __init__(self, origen: str, segundos: float):
        self.segundos = float(segundos)
        super().__init__("foro", origen, self.segundos, "flood")


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


def _sin_parametros_de_sesion(url: str) -> str:
    """Quita de la query los parámetros de sesión (`s=`, `sid`…), conservando los demás.

    m-2 (SecOps): un `topic_url` con `s=` propaga la sesión a la UI/BD; `showtopic=N` y los
    parámetros no sensibles se conservan porque forman parte del enlace.
    """
    try:
        partes = urlsplit(url)
    except ValueError:
        return url
    if not partes.query:
        return url
    pares = [(clave, valor) for clave, valor in parse_qsl(partes.query, keep_blank_values=True)
             if clave.lower() not in _PARAMS_DE_SESION]
    return urlunsplit((partes.scheme, partes.netloc, partes.path,
                       urlencode(pares, doseq=True), ""))


def url_de_foro_visible(url: str) -> str:
    """URL del foro para pintar/registrar: sin credenciales, query de sesión ni fragmento (m-1).

    Devuelve `""` si no es una URL http(s) con host; así Ajustes y el diagnóstico nunca muestran
    `user:pass@` ni `?s=<sesión>` aunque el `.env` venga mal.
    """
    try:
        partes = urlsplit(str(url).strip())
        puerto = partes.port
    except (ValueError, AttributeError):
        return ""
    esquema = partes.scheme.lower()
    host = (partes.hostname or "").lower()
    if esquema not in _PUERTOS_POR_DEFECTO or not host:
        return ""
    netloc = host
    if puerto is not None and puerto != _PUERTOS_POR_DEFECTO[esquema]:
        netloc = f"{host}:{puerto}"
    return urlunsplit((esquema, netloc, partes.path or "/", "", ""))


def _host_para_log(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "?")[:100]
    except ValueError:
        return "?"


def _codec(nombre: str | None) -> str | None:
    """Nombre canónico del codec si Python lo conoce; None si no (nunca se confía en la fuente)."""
    if not nombre:
        return None
    try:
        return codecs.lookup(nombre.strip().strip("\"'")).name
    except (LookupError, ValueError, TypeError):
        return None


def _charset_de_cabecera(respuesta: httpx.Response) -> str | None:
    cabecera = respuesta.headers.get("content-type", "") or ""
    for parte in cabecera.split(";"):
        nombre, _, valor = parte.partition("=")
        if nombre.strip().lower() == "charset":
            return _codec(valor)
    return None


def _charset_de_meta(contenido: bytes) -> str | None:
    """`<meta charset>` o `<meta http-equiv=content-type …>` en los primeros 4 KiB."""
    muestra = contenido[:MAX_BYTES_CHARSET].decode("latin-1", errors="replace")
    directo = re.search(r"<meta[^>]+charset\s*=\s*[\"']?([A-Za-z0-9._:-]+)", muestra,
                        re.IGNORECASE)
    if directo:
        return _codec(directo.group(1))
    http_equiv = re.search(
        r"<meta[^>]+http-equiv\s*=\s*[\"']?content-type[\"']?[^>]+"
        r"content\s*=\s*[\"'][^\"']*charset\s*=\s*([A-Za-z0-9._:-]+)",
        muestra, re.IGNORECASE)
    if http_equiv:
        return _codec(http_equiv.group(1))
    return None


def analizar_charset(respuesta: httpx.Response) -> tuple[str | None, str | None, str]:
    """`(charset de cabecera, charset de meta, usado)` de una respuesta.

    Prioridad: cabecera válida → meta válida → **cp1252** con aviso (nunca UTF-8 a ciegas).
    Los nombres se devuelven canónicos (p. ej. `iso8859-1`), listos para `encode`/`quote`.
    """
    cabecera = _charset_de_cabecera(respuesta)
    if cabecera is not None:
        return cabecera, _charset_de_meta(respuesta.content), cabecera
    meta = _charset_de_meta(respuesta.content)
    if meta is not None:
        return None, meta, meta
    logger.warning("forum.charset_no_declarado", host=_host_para_log(str(respuesta.url)))
    return None, None, "cp1252"


def detectar_charset(respuesta: httpx.Response) -> str:
    """Atajo de `analizar_charset`: el charset con el que hay que decodificar/enviar."""
    return analizar_charset(respuesta)[2]


def decodificar_respuesta(respuesta: httpx.Response,
                          charset: str | None = None) -> tuple[str, str]:
    """`(texto, charset usado)`: decodifica los BYTES, nunca `respuesta.text` (UTF-8 ciego)."""
    usado = charset or detectar_charset(respuesta)
    return respuesta.content.decode(usado, errors="replace"), usado


def detectar_flood(html: str) -> float | None:
    """Segundos de espera si la página es un aviso de flood de IPB; `None` si no lo es.

    Exige la caja de error de IPB **y** una frase de saturación, para no confundir prosa que
    mencione «búsqueda». Recorta a [20, 60] s y usa 30 s si la página no dice cuánto.
    """
    if not _RE_CAJA_ERROR.search(html) or not _RE_FRASE_FLOOD.search(html):
        return None
    coincidencia = _RE_SEGUNDOS_FLOOD.search(html)
    segundos = float(coincidencia.group(1)) if coincidencia else FLOOD_POR_DEFECTO_S
    return min(FLOOD_MAX_S, max(FLOOD_MIN_S, segundos))


@dataclass
class ForumResult:
    topic_title: str
    topic_url: str
    ed2k_links: list[str] = field(default_factory=list)
    magnet_links: list[str] = field(default_factory=list)


class ForumScraper:
    def __init__(self, base_url: str, rate_limit: float | None = None,
                 crear_cliente: Callable[[], httpx.AsyncClient] | None = None, *,
                 politica: PoliticaFuente | None = None,
                 politica_busqueda: PoliticaFuente | None = None,
                 cortesia: CortesiaProceso | None = None,
                 reloj=time.monotonic, dormir=asyncio.sleep, espera_max_s: float = 30.0):
        visible = url_de_foro_visible(base_url)
        self._base = (visible or base_url).rstrip("/")
        self._origen = origen_de(self._base)
        ajustes = get_settings()
        # AC-INT-4: lectura y búsqueda salen de config.py; `rate_limit=` se conserva para los
        # dobles de prueba que fuerzan 0 s y para el orquestador (compatibilidad).
        intervalo_lectura = (float(rate_limit) if rate_limit is not None
                             else float(getattr(ajustes, "forum_rate_limit", 2.0)))
        intervalo_busqueda = float(getattr(ajustes, "forum_search_rate_limit",
                                           intervalo_lectura or 2.0))
        self._politica = politica or PoliticaFuente(
            "foro", "Foro", max(0.0, intervalo_lectura), max_intentos=2,
            max_redirecciones=MAX_SALTOS)
        self._politica_busqueda = politica_busqueda or PoliticaFuente(
            "foro", "Foro", max(0.0, intervalo_busqueda), max_intentos=1,
            max_redirecciones=MAX_SALTOS)
        self._espera_busqueda_s = max(30.0, self._politica_busqueda.intervalo_min_s + 5.0)
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._cookies: dict = {}
        self._charset: str | None = None
        #: `(cabecera, meta, usado)` del último GET de entrada; lo usa el script de diagnóstico.
        self.charset_entrada: tuple[str | None, str | None, str] | None = None
        #: Código HTTP del GET de entrada y nº de cookies recibidas (NUNCA sus valores).
        self.estado_entrada: int | None = None
        self.cookies_recibidas = 0
        # Las pruebas inyectan un cliente con transporte simulado. Sin redirecciones automáticas.
        self._crear_cliente = crear_cliente or (
            lambda: httpx.AsyncClient(timeout=30.0, follow_redirects=False))

    # ── cortesía y red ──────────────────────────────────────────────────────────────────────
    def _cortesia_actual(self) -> CortesiaProceso:
        if self._cortesia is None:
            self._cortesia = cortesia_de_proceso()
        return self._cortesia

    async def _pedir(self, url: str, *, client: httpx.AsyncClient | None = None,
                     datos=None, form: bool = False,
                     politica: PoliticaFuente | None = None,
                     espera_max_s: float | None = None,
                     form_charset: str | None = None) -> httpx.Response:
        """Una petición por la envoltura común; reutiliza el cliente si se pasa uno."""
        propio = client is None
        cliente = client or self._crear_cliente()
        try:
            return await pedir_con_cortesia(
                cliente, "POST" if form else "GET", url,
                politica=politica or self._politica,
                espera_max_s=self._espera_max_s if espera_max_s is None else espera_max_s,
                datos=datos, form=form, form_charset=form_charset,
                cabeceras=self._cabeceras(url),
                cortesia=self._cortesia_actual(),
                reloj=self._reloj, dormir=self._dormir,
            )
        finally:
            if propio:
                await cliente.aclose()

    def _comprobar_flood(self, html: str) -> None:
        """Detecta la página de saturación, comparte el bloqueo y lanza `ForumFloodControl`."""
        segundos = detectar_flood(html)
        if segundos is None:
            return
        origen = origen_normalizado(self._base)
        self._cortesia_actual().bloquear("foro", origen, segundos, motivo="flood")
        logger.info("forum.flood_control", segundos=segundos)
        raise ForumFloodControl(origen, segundos)

    def _decodificar(self, respuesta: httpx.Response) -> str:
        texto, usado = decodificar_respuesta(respuesta)
        if self._charset is None:
            self._charset = usado
        return texto

    # ── login ──────────────────────────────────────────────────────────────────────────────
    async def _leer_entrada(self, cliente: httpx.AsyncClient | None = None) -> str:
        """GET de `index.php`: charset, cookies de visita y formulario de login real."""
        respuesta = await self._pedir(f"{self._base}/index.php", client=cliente)
        self.estado_entrada = respuesta.status_code
        self.charset_entrada = analizar_charset(respuesta)
        self._charset = self.charset_entrada[2]
        html = self._decodificar(respuesta)
        self._comprobar_flood(html)
        return html

    def _formulario_de_login(self, html: str) -> tuple[str | None, dict[str, str]]:
        """`(acción real del formulario de login | None, campos ocultos)`, con `s=` conservado."""
        try:
            documento = document_fromstring(html, parser=HTMLParser(
                recover=True, no_network=True))
        except (ValueError, SyntaxError, etree.ParserError):
            return None, {}
        formularios = documento.xpath(
            "//form[.//input[@name='UserName'] or .//input[@name='PassWord']]")
        if not formularios:
            return None, {}
        formulario = formularios[0]
        accion = formulario.get("action")
        ocultos: dict[str, str] = {}
        for campo in formulario.xpath(".//input[@type='hidden'][@name]"):
            ocultos[campo.get("name")] = campo.get("value") or ""
        return accion, ocultos

    @property
    def nombres_de_cookies(self) -> list[str]:
        """Nombres de las cookies recibidas (nunca los valores): ayuda a diagnosticar el login."""
        return sorted(self._cookies)

    async def login(self, username: str, password: str) -> bool:
        if self._origen is None:
            raise OrigenNoPermitidoError("foro_sin_origen")
        cliente = self._crear_cliente()
        try:
            html = await self._leer_entrada(cliente)
            accion, ocultos = self._formulario_de_login(html)
            if accion:
                destino = self._resolver_enlace(
                    accion, conservar_sesion=True)           # AC-CHA-6: mismo origen o error
            else:
                destino = f"{self._base}/index.php?act=Login&CODE=01"
            datos = {**ocultos, "UserName": username, "PassWord": password, "CookieDate": "1"}
            respuesta = await self._pedir(
                destino, client=cliente, datos=datos, form=True,
                form_charset=self._charset or "cp1252")
            # El jar del cliente conserva Set-Cookie de un 302 intermedio (IPB responde así);
            # `respuesta.cookies` de la final llegaría vacío.
            for clave, valor in cliente.cookies.items():
                self._cookies[clave] = valor
            self.cookies_recibidas = len(self._cookies)
            self._comprobar_flood(self._decodificar(respuesta))
        finally:
            await cliente.aclose()
        confirmado = any(
            es_cookie_de_miembro(clave) and str(valor) not in ("", "0")
            for clave, valor in self._cookies.items()
        )
        if not confirmado:
            logger.info("forum.login_no_confirmado", host=_host_para_log(self._base))
        return confirmado

    # ── cabeceras y enlaces (H5: no tocar la frontera de origen) ──────────────────────────
    def _cabeceras(self, url: str) -> dict[str, str]:
        """Las cookies SOLO acompañan a una petición del origen exacto del foro."""
        cabeceras = {"User-Agent": USER_AGENT}
        if self._cookies and self._origen is not None and origen_de(url) == self._origen:
            cabeceras["Cookie"] = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
        return cabeceras

    def _resolver_enlace(self, href: str, *, conservar_sesion: bool = False) -> str:
        """URL absoluta del enlace, SOLO si es del origen del foro; si no, se lanza el error.

        Por defecto quita de la query los parámetros de sesión (`s=`): el enlace se guarda y se
        pinta, así que no debe propagar la sesión (m-2). El login pide `conservar_sesion=True`.
        """
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
            if "@" in partes.netloc or partes.username is not None or partes.password is not None:
                raise OrigenNoPermitidoError("credenciales_en_la_url")
            esquema = partes.scheme or self._origen[0]
            if origen_de(f"{esquema}://{partes.netloc}/") != self._origen:
                raise OrigenNoPermitidoError("otro_origen")
            ruta = "/" + partes.path.lstrip("/")
            href = ruta + (f"?{partes.query}" if partes.query else "")
        try:
            url = urljoin(self._base + "/", href)
        except ValueError:
            raise OrigenNoPermitidoError("url_mal_formada") from None
        if origen_de(url) != self._origen:
            raise OrigenNoPermitidoError("otro_origen")
        if not conservar_sesion:
            url = _sin_parametros_de_sesion(url)
        return url

    async def _get(self, url: str, *, politica: PoliticaFuente | None = None,
                   espera_max_s: float | None = None) -> str:
        """GET de una página del foro, decodificada en su charset real (sin `r.text`)."""
        if origen_de(url) != self._origen:
            raise OrigenNoPermitidoError("otro_origen")
        try:
            respuesta = await self._pedir(url, politica=politica,
                                          espera_max_s=espera_max_s)
        except RedireccionNoPermitida as exc:
            motivos = {
                "otro_origen": "otro_origen",
                "location_ausente": "redireccion_sin_destino",
                "location_con_credenciales": "credenciales_en_la_url",
            }
            raise OrigenNoPermitidoError(motivos.get(exc.motivo, "url_mal_formada")) from exc
        except DemasiadasRedirecciones as exc:
            raise OrigenNoPermitidoError("demasiadas_redirecciones") from exc
        texto = self._decodificar(respuesta)
        self._comprobar_flood(texto)
        return texto

    def _enlaces_del_tema(self, topic_html: str, url: str,
                          title: str) -> ForumResult:
        ed2k = list(dict.fromkeys(ED2K_PATTERN.findall(topic_html)))
        magnets = list(dict.fromkeys(MAGNET_PATTERN.findall(topic_html)))
        return ForumResult(title.strip(), url, ed2k, magnets)

    async def leer_tema(self, url: str) -> ForumResult:
        """Lee un tema concreto y devuelve sus enlaces (una sola petición)."""
        if origen_de(url) != self._origen:
            raise OrigenNoPermitidoError("otro_origen")
        html = await self._get(url)
        return self._enlaces_del_tema(html, url, "")

    async def use_ipb_search(self, query: str, *, abrir_temas: bool = True) -> list[ForumResult]:
        """Busca en el foro. Un flood lanza; un vacío real devuelve `[]`."""
        charset = self._charset or "cp1252"
        try:
            termino = quote(query, encoding=charset)
        except UnicodeEncodeError:
            # Un carácter fuera del charset se sustituye en cp1252 (el foro no lo entendería
            # igual, pero no se rompe la búsqueda ni se filtra la query al log).
            termino = quote(query, encoding="cp1252", errors="replace")
        url = (f"{self._base}/index.php?act=Search&CODE=01&keywords={termino}"
               "&searchin=titles")
        try:
            html = await self._get(url, politica=self._politica_busqueda,
                                   espera_max_s=self._espera_busqueda_s)
        except OrigenNoPermitidoError as exc:
            logger.warning("forum.search_rechazada", motivo=str(exc))
            return []
        except (CortesiaEnEspera, FuenteApagada):
            # AC-16: una espera o una fuente apagada NO es «sin resultados» ni un fallo.
            raise
        except Exception as exc:
            # m-3 (SecOps): tipo del error, nunca la excepción/URL con `s=` (privacidad §6.6).
            logger.warning("forum.search_failed", error=type(exc).__name__)
            return []
        results: list[ForumResult] = []
        for href, title in TOPIC_PATTERN.findall(html)[:10]:
            href = unescape(href)  # `&amp;` del HTML, no parte de la ruta
            try:
                url_tema = self._resolver_enlace(href)
            except OrigenNoPermitidoError as exc:
                logger.warning("forum.enlace_rechazado", host=_host_para_log(href),
                               motivo=str(exc))
                continue
            if not abrir_temas:
                results.append(ForumResult(title.strip(), url_tema))
                continue
            try:
                topic_html = await self._get(url_tema)
                results.append(self._enlaces_del_tema(topic_html, url_tema, title))
            except OrigenNoPermitidoError as exc:
                logger.warning("forum.tema_rechazado", motivo=str(exc))
            except (CortesiaEnEspera, FuenteApagada):
                raise
            except Exception as exc:
                # Solo el host y el tipo: la URL del tema puede llevar `s=<sesión>` (m-3).
                logger.warning("forum.topic_failed", host=_host_para_log(url_tema),
                               error=type(exc).__name__)
        return results
