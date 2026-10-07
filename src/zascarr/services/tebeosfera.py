"""
Cliente Tebeosfera (scraping) — fuente del enricher para las tradiciones
tebeo y franco_belgian (grapa/álbum en español; confirmado con búsquedas
reales — "Thorgal", BD franco-belga, aparece en Tebeosfera con ediciones
españolas de Distrinovel/Zinco/Norma).

Tebeosfera no tiene API pública: esto es scraping de dos endpoints AJAX
internos de su propio buscador (los mismos que usa su frontend). Portado
con inspiración directa de theotocopulitos/tebeosfera-scraper (Apache
2.0) — ese proyecto documentó los endpoints y la estructura HTML de la
que parte este cliente; gracias a su parser de 700 líneas para la ficha
completa de un número, que confirmó que replicarlo entero es un proyecto
en sí mismo y no algo para portar de una sentada.

Endpoints (confirmados en vivo contra tebeosfera.com, no solo leídos del
repo de referencia — el sitio puede haber cambiado desde que se escribió):
  POST /neko/templates/ajax/buscador_txt_post.php
       {tabla: "T3_publicaciones", busqueda: <query>}  → colecciones
       {tabla: "T3_series",        busqueda: <query>}  → sagas
Cada resultado es un <div class="linea_resultados"> con un <a href="/
colecciones/{slug}.html"> o <a href="/sagas/{slug}.html"> cuyo texto es
el título CON un sufijo "(año, editorial)" pegado que hay que limpiar
antes de comparar contra Series.title.

Fragilidad asumida: al no ser una API con contrato, cualquier rediseño
del sitio puede romper este cliente sin aviso. Por eso el rate limit es
más conservador que el de Comic Vine/AniList, y cualquier fallo de red o
de parseo se trata como "sin resultado" (nunca como excepción que tumbe
el ciclo del enricher — ver enricher.py, que ya envuelve esto en su
propio try/except de todos modos, pero el propio cliente no debe ni
necesita propagar fallos de parseo HTML como errores duros).

Cortesía (decisión del PROYECTO, conservadora; no una afirmación sobre la política oficial del
sitio): **2,5 s como mínimo entre peticiones**, compartido por TODAS las instancias y caminos del
proceso (`utils/cortesia.py`): la búsqueda de Descubrir y el enricher llegan al sitio por el mismo
limitador, cada salto HTTP incluido (las redirecciones se siguen a mano, ≤ 3 y solo al propio
origen). Depende de que haya un solo proceso (`uvicorn --workers 1`). Una configuración por
debajo del mínimo se eleva a él.

Alcance deliberado: solo a nivel de SERIE (título, portada, año, nº de
números). Sinopsis/créditos por número requerirían parsear la ficha
completa de cada número — fuera de alcance de esta primera pasada, igual
que AniList solo enriquece a nivel de serie.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
import structlog
from lxml import html as lxml_html

from zascarr.config import get_settings
from zascarr.utils.cortesia import limitador_de

logger = structlog.get_logger()

_BASE_URL = "https://www.tebeosfera.com"
SITIO = "tebeosfera"
#: Mínimo entre peticiones, en segundos. Decisión del proyecto (revisión del 2026-10-07): es una
#: asociación cultural sin ánimo de lucro y un scraping sin contrato; se prefiere pecar de cortés.
#: Solo se puede SUBIR.
MINIMO_ENTRE_PETICIONES_S = 2.5
#: Saltos de redirección que se siguen como máximo. Cada salto es una petición más al sitio y pasa
#: por el limitador (2,5 s), igual que la inicial; se siguen A MANO, no con `follow_redirects`.
MAX_SALTOS = 3
_REDIRECCIONES = (301, 302, 303, 307, 308)
_SEARCH_ENDPOINT = "/neko/templates/ajax/buscador_txt_post.php"



def destino_permitido(url: str) -> bool:
    """Política de redirecciones: solo el ORIGEN del sitio (esquema, host y puerto de `_BASE_URL`),
    sin credenciales. Cualquier otro destino (otro host, http, otro puerto, CDN, `//otrohost`) se
    rechaza."""
    try:
        destino, base = urlsplit(url), urlsplit(_BASE_URL)
        puerto = 443 if base.scheme == "https" else 80
        return (destino.scheme == base.scheme and destino.hostname == base.hostname
                and destino.port in (None, base.port, puerto)
                and destino.username is None and destino.password is None)
    except ValueError:
        return False


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
# \d{1,4}, no \d+: ninguna colección real tiene 5+ dígitos de números. Si
# algún otro artefacto de concatenación cuela un número disparatado, que
# el regex no lo capture es más seguro que capturarlo y confiar en él.
_COUNT_RE = re.compile(r"(\d{1,4})\s*n[uú]meros?", re.IGNORECASE)
# "THORGAL (1981, DISTRINOVEL)" / "THORGAL (1990, NORMA) -SUBCOLECCION-"
# → "THORGAL": todo lo que sigue al primer paréntesis es ruido de catálogo,
# nunca parte del nombre real de la serie.
_TITLE_SUFFIX_RE = re.compile(r"\s*\([^)]*\).*$")


@dataclass
class TebeosferaResult:
    slug: str
    title: str  # ya limpio de sufijo "(año, editorial)"
    kind: str  # "collection" | "saga"
    start_year: int | None = None
    count_of_issues: int | None = None
    cover_url: str | None = None
    description: str | None = None  # solo disponible a veces, en sagas
    site_url: str | None = None


class TebeosferaClient:
    def __init__(self, transporte: httpx.AsyncBaseTransport | None = None):
        # `transporte`: solo para pruebas (un transporte simulado); en producción es siempre None.
        s = get_settings()
        configurado = float(s.tebeosfera_rate_limit)
        if configurado < MINIMO_ENTRE_PETICIONES_S:
            logger.warning("tebeosfera.rate_limit_elevado", configurado=configurado,
                           minimo=MINIMO_ENTRE_PETICIONES_S)
        self._rate_limit = max(configurado, MINIMO_ENTRE_PETICIONES_S)
        self._transporte = transporte
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            transport=self._transporte,
            base_url=_BASE_URL, timeout=30.0, follow_redirects=False,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; ZascArr/0.1; +comic library manager)",
                "Referer": _BASE_URL + "/",
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        """Espera según el limitador COMPARTIDO del sitio, no el de la instancia."""
        await limitador_de(SITIO).esperar(self._rate_limit)

    async def _enviar(self, metodo: str, url: str, data: dict | None) -> httpx.Response:
        """Cada petición al sitio, incluida cada redirección, espera en el limitador compartido.

        Las redirecciones se siguen a mano (hasta `MAX_SALTOS`) y solo hacia el origen del sitio
        (`destino_permitido`); 301/302/303 pasan a GET sin cuerpo, 307/308 conservan método y
        cuerpo. Un destino no permitido, demasiados saltos o una redirección sin `Location`
        lanzan `httpx.HTTPError` (el llamador lo trata como «sin resultados»)."""
        assert self._client is not None
        for _ in range(MAX_SALTOS + 1):
            await self._throttle()
            r = await self._client.request(metodo, url, data=data)
            if r.status_code not in _REDIRECCIONES:
                return r
            destino = r.headers.get("location")
            try:
                absoluto = urljoin(str(r.url), destino) if destino else ""
            except ValueError:
                absoluto = ""
            if not absoluto or not destino_permitido(absoluto):
                # Solo el host en el registro: la URL puede llevar datos de la búsqueda.
                logger.warning("tebeosfera.redireccion_rechazada",
                               host=urlsplit(absoluto).hostname if absoluto else None)
                raise httpx.TooManyRedirects("destino de redirección no permitido",
                                             request=r.request)
            if r.status_code in (301, 302, 303):
                metodo, data = "GET", None
            url = absoluto
        logger.warning("tebeosfera.demasiadas_redirecciones", saltos=MAX_SALTOS)
        raise httpx.TooManyRedirects("demasiadas redirecciones", request=r.request)

    async def _search_table(self, tabla: str, kind: str, query: str) -> list[TebeosferaResult]:
        try:
            r = await self._enviar("POST", _SEARCH_ENDPOINT, {"tabla": tabla, "busqueda": query})
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("tebeosfera.request_failed", tabla=tabla, query=query, error=str(exc))
            return []
        return _parse_results(r.text, kind)

    async def search_series(self, query: str, limit: int = 10) -> list[TebeosferaResult]:
        """Busca en colecciones (ediciones/tiradas concretas) y sagas (la
        obra en su conjunto): dos peticiones, el doble que Comic Vine/
        AniList — ver la nota de rate limit en config.py."""
        collections = await self._search_table("T3_publicaciones", "collection", query)
        sagas = await self._search_table("T3_series", "saga", query)
        return (collections + sagas)[:limit]


def _parse_results(html_fragment: str, kind: str) -> list[TebeosferaResult]:
    if not html_fragment or "linea_resultados" not in html_fragment:
        return []
    try:
        tree = lxml_html.fromstring(html_fragment)
    except Exception:
        logger.warning("tebeosfera.parse_failed", kind=kind)
        return []

    path = "/colecciones/" if kind == "collection" else "/sagas/"
    results = []
    for row in tree.xpath('//div[contains(@class, "linea_resultados")]'):
        links = row.xpath(f'.//a[contains(@href, "{path}")]')
        if not links:
            continue
        href = links[0].get("href", "")
        slug_match = re.search(rf'{re.escape(path)}([^/]+)\.html', href)
        raw_title = (links[0].text_content() or "").strip()
        if not slug_match or not raw_title:
            continue

        title = _TITLE_SUFFIX_RE.sub("", raw_title).strip()
        # text_content() concatena texto sin insertar espacio donde hubiera
        # un <br>: "1986 a 1988<br>4 números" se convierte en "19884
        # números" y el regex de conteo lee 19884 en vez de 4. Confirmado
        # en vivo contra tebeosfera.com, no una hipótesis: sin este fix,
        # el conteo de números salía disparatado en varias colecciones.
        for br in row.xpath(".//br"):
            br.tail = "\n" + (br.tail or "")
        row_text = row.text_content()
        year_match = _YEAR_RE.search(row_text)
        count_match = _COUNT_RE.search(row_text)
        thumb = row.xpath(".//img/@src")

        results.append(TebeosferaResult(
            slug=slug_match.group(1),
            title=title,
            kind=kind,
            start_year=int(year_match.group(0)) if year_match else None,
            count_of_issues=int(count_match.group(1)) if count_match else None,
            cover_url=thumb[0] if thumb else None,
            site_url=f"{_BASE_URL}{href}",
        ))
    return results
