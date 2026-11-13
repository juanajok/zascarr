"""Adaptador de Continuity Guide (continuityguide.net) — SCR3 entrega 1.

La página es un HTML de Squarespace sin `h1`/`h2` (no se puede leer el orden por encabezados):
las entradas son los `div.image-card` **en orden DOM**. En cada tarjeta, cada `p` de
`.image-subtitle` con `#` es una referencia fáctica («Daredevil (1998) #1-8»); el `p` hermano
entre comillas es título de arco y se descarta, igual que cualquier `p` con `#` fuera de una
tarjeta (prosa o referencias sueltas). Prohibido `?format=json` (lo veta el `robots.txt`).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin, urlsplit

import structlog
from lxml.html import HTMLParser, document_fromstring

from zascarr.services.reading_orders.comun import (
    ExtractorGuias,
    GuiaLeida,
    RawReadingEntry,
    _texto,
)

logger = structlog.get_logger()

#: Origen y sitemap (verificados en vivo el 2026-11-13: `urlset` con 4.253 `<loc>` mezclando
#: páginas e `images.squarespace-cdn.com`; se filtra por host y extensión).
ORIGEN = "https://www.continuityguide.net"
SITEMAP = f"{ORIGEN}/sitemap.xml"
HOSTS_PERMITIDOS = ("www.continuityguide.net",)
#: Extensiones que NO son guías (imágenes del CDN, estáticos, sitemaps, etc.).
_RE_EXTENSION = re.compile(
    r"\.(?:jpe?g|png|gif|webp|avif|svg|ico|css|js|json|xml|pdf|zip|txt|woff2?)$",
    re.IGNORECASE)


class ContinuityGuideExtractor(ExtractorGuias):
    """Lee una página de Continuity Guide: tarjetas en orden DOM y la referencia con `#`."""

    sitio = "continuity_guide"
    hosts_permitidos = HOSTS_PERMITIDOS

    @property
    def sitemap_url(self) -> str:
        return SITEMAP

    def _url_del_sitio(self, url: str) -> bool:
        try:
            partes = urlsplit(url)
        except ValueError:
            return False
        if partes.scheme != "https":
            return False
        if (partes.hostname or "").lower() not in HOSTS_PERMITIDOS:
            return False
        # `robots.txt` de la guía prohíbe cualquier query (`?format=json` incluida).
        return not partes.query

    def _filtrar_sitemap(self, url: str) -> bool:
        if not self._url_del_sitio(url):
            return False
        ruta = urlsplit(url).path
        return bool(ruta) and ruta != "/" and _RE_EXTENSION.search(ruta) is None

    def _parsear(self, contenido: bytes, url: str) -> GuiaLeida | None:
        documento = document_fromstring(
            contenido, parser=HTMLParser(recover=True, no_network=True))
        if documento is None:
            return None
        titulo = _texto(documento.xpath("//title"))
        tarjetas = documento.xpath(
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' image-card ')]")
        entradas: list[RawReadingEntry] = []
        for tarjeta in tarjetas:
            subtitulos = tarjeta.xpath(
                ".//p[contains(concat(' ', normalize-space(@class), ' '), "
                "' image-subtitle ')]")
            if not subtitulos:
                # Algunas maquetas envuelven los `p` en un contenedor `.image-subtitle`.
                subtitulos = tarjeta.xpath(
                    ".//*[contains(concat(' ', normalize-space(@class), ' '), "
                    "' image-subtitle ')]//p")
            for parrafo in subtitulos:
                referencia = _texto([parrafo])
                if not referencia or "#" not in referencia:
                    continue                # título de arco entre comillas o prosa: fuera
                enlaces = parrafo.xpath(".//a[@href]/@href")
                item_url = urljoin(url, enlaces[0]) if enlaces else None
                entradas.append(RawReadingEntry(
                    orden=len(entradas) + 1, referencia=referencia,
                    seccion=None, item_url=item_url))
        if not entradas:
            return None
        return GuiaLeida(sitio=self.sitio, url=url, titulo=titulo,
                         entradas=tuple(entradas))


__all__ = ["HOSTS_PERMITIDOS", "ORIGEN", "SITEMAP", "ContinuityGuideExtractor"]
