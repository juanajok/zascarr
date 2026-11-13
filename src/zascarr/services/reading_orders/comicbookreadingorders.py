"""Adaptador de Comic Book Reading Orders (comicbookreadingorders.com) — SCR3 entrega 1.

La guía es HTML clásico (WordPress): `main > h1` con el título y un `ol.issues` cuyos `li`
directos pueden ser de tres clases: `li.issue` (un número), un `li` con `h2` (sección) o
`li.aside.note-row` (prosa, que **no** se lee). Del `li.issue` se toman solo hechos:
`div.issue-main > span.issue-title`, el `span.year` si consta (se añade entre paréntesis
para que el resolver lo trate como año del número) y el `a.read-link`.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import structlog
from lxml.html import HTMLParser, document_fromstring

from zascarr.services.reading_orders.comun import (
    ExtractorGuias,
    GuiaLeida,
    RawReadingEntry,
    _texto,
    entrada_de_guia,
    url_de_sitio_valida,
)

logger = structlog.get_logger()

#: Origen y sitemap (verificados en vivo el 2026-11-13; `urlset` sin índice de sitemaps).
ORIGEN = "https://comicbookreadingorders.com"
SITEMAP = f"{ORIGEN}/sitemap.xml"
HOSTS_PERMITIDOS = ("comicbookreadingorders.com", "www.comicbookreadingorders.com")
#: Las guías del sitemap: eventos/personajes de Marvel o DC, con sufijo de orden de lectura.
_RE_GUIA = re.compile(
    r"^/(?:marvel|dc)/(?:events|characters)/.+-(?:master-)?reading-order/?$")
#: Rutas que el `robots.txt` del sitio prohíbe y que aquí se rechazan antes de pedir.
RUTAS_PROHIBIDAS = ("/api/", "/search/", "/admin/")


class ReadingOrdersExtractor(ExtractorGuias):
    """Lee guías de Comic Book Reading Orders: orden, referencia y enlace «Read»."""

    sitio = "reading_orders"
    hosts_permitidos = HOSTS_PERMITIDOS

    @property
    def sitemap_url(self) -> str:
        return SITEMAP

    def _url_del_sitio(self, url: str) -> bool:
        # SecOps m-3: https, host allowlist, sin userinfo, puerto 443, sin query ni recursos.
        return url_de_sitio_valida(url, HOSTS_PERMITIDOS,
                                   rutas_prohibidas=RUTAS_PROHIBIDAS)

    def _filtrar_sitemap(self, url: str) -> bool:
        if not self._url_del_sitio(url):
            return False
        return _RE_GUIA.match(urlsplit(url).path) is not None

    def _parsear(self, contenido: bytes, url: str) -> GuiaLeida | None:
        documento = document_fromstring(
            contenido, parser=HTMLParser(recover=True, no_network=True))
        if documento is None:
            return None
        titulo = _texto(documento.xpath("//main/h1")) or _texto(documento.xpath("//h1"))
        listas = documento.xpath(
            "//ol[contains(concat(' ', normalize-space(@class), ' '), ' issues ')]")
        if not listas:
            return None
        entradas: list[RawReadingEntry] = []
        seccion: str | None = None
        for hijo in listas[0].xpath("./li"):
            clases = (hijo.get("class") or "").split()
            if "aside" in clases or "note-row" in clases:
                continue                    # prosa del autor: nunca se lee
            encabezados = hijo.xpath("./h2")
            if encabezados:
                seccion = _texto(encabezados)
                continue
            if "issue" not in clases:
                continue
            principales = hijo.xpath(
                ".//div[contains(concat(' ', normalize-space(@class), ' '), ' issue-main ')]")
            if not principales:
                continue
            referencia = _texto(principales[0].xpath(
                ".//span[contains(concat(' ', normalize-space(@class), ' '), "
                "' issue-title ')]"))
            if not referencia:
                continue
            anio = _texto(principales[0].xpath(
                ".//span[contains(concat(' ', normalize-space(@class), ' '), ' year ')]"))
            if anio:
                referencia = f"{referencia} ({anio})"
            enlaces = hijo.xpath(
                ".//a[contains(concat(' ', normalize-space(@class), ' '), "
                "' read-link ')][@href]/@href")
            entrada = entrada_de_guia(
                orden=len(entradas) + 1, referencia=referencia, seccion=seccion,
                href=enlaces[0] if enlaces else None, base_url=url)
            if entrada is not None:           # cotas + enlace solo http(s) (m-2/m-5)
                entradas.append(entrada)
        if not entradas:
            return None
        return GuiaLeida(sitio=self.sitio, url=url, titulo=titulo,
                         entradas=tuple(entradas))


__all__ = ["HOSTS_PERMITIDOS", "ORIGEN", "RUTAS_PROHIBIDAS", "SITEMAP", "ReadingOrdersExtractor"]
