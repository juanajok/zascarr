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

Alcance deliberado: solo a nivel de SERIE (título, portada, año, nº de
números). Sinopsis/créditos por número requerirían parsear la ficha
completa de cada número — fuera de alcance de esta primera pasada, igual
que AniList solo enriquece a nivel de serie.
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import httpx, structlog
from lxml import html as lxml_html

from secuenciarr.config import get_settings

logger = structlog.get_logger()

_BASE_URL = "https://www.tebeosfera.com"
_SEARCH_ENDPOINT = "/neko/templates/ajax/buscador_txt_post.php"

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


class TebeosferaClient:
    def __init__(self):
        s = get_settings()
        self._rate_limit = s.tebeosfera_rate_limit
        self._last_req: float = 0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL, timeout=30.0, follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; SecuenciArr/0.1; +comic library manager)",
                "Referer": _BASE_URL + "/",
                "Accept-Language": "es-ES,es;q=0.9",
            },
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        now = asyncio.get_event_loop().time()
        if (elapsed := now - self._last_req) < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        self._last_req = asyncio.get_event_loop().time()

    async def _search_table(self, tabla: str, kind: str, query: str) -> list[TebeosferaResult]:
        assert self._client is not None
        await self._throttle()
        try:
            r = await self._client.post(_SEARCH_ENDPOINT, data={"tabla": tabla, "busqueda": query})
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
        ))
    return results
