"""Extractores de guías y órdenes de lectura (SCR3, entrega 1; sin modelo ni UI).

Dos adaptadores con el mismo contrato:

- `ReadingOrdersExtractor` (comicbookreadingorders.com): HTML clásico, `ol.issues`,
  secciones por `h2` y año del número en `span.year`.
- `ContinuityGuideExtractor` (continuityguide.net): tarjetas `.image-card` en orden DOM; sin
  encabezados y sin `?format=json` (robots).

Ambos: descubrimiento por `sitemap.xml`, descarga por la caché/robots de SCR1
(`utils/cache_http`), tope de 2 MiB, parseo en `asyncio.to_thread` y **solo hechos** (orden,
referencia, sección y enlace); nunca la prosa del autor. Un fallo esperable devuelve `None` o
`[]` con log estructurado, nunca una excepción al orquestador.

La normalización de cada referencia a `(serie, año, número/rango)` vive en
`services/reading_order_resolver.py` (puro) y la reconciliación con la biblioteca (sobre
`story_arcs`, sin modelo nuevo) en `services/reconciliacion_lecturas.py`. Las fuentes se
estrenan **apagadas** (ADR 0013) y se encienden en Ajustes; con la fuente apagada el
extractor devuelve vacío sin tocar la red.
"""
from __future__ import annotations

from zascarr.services.reading_orders.comicbookreadingorders import ReadingOrdersExtractor
from zascarr.services.reading_orders.comun import (
    MAX_CUERPO,
    MAX_CUERPO_HTML,
    MAX_CUERPO_SITEMAP,
    MAX_GUIAS,
    MAX_LOCS,
    MAX_REFERENCIA,
    MAX_SECCION,
    MAX_TITULO_GUIA,
    MAX_URL_ITEM,
    POLITICA_CACHE_GUIA,
    POLITICA_CACHE_SITEMAP,
    ExtractorGuias,
    GuiaLeida,
    GuiaResumen,
    RawReadingEntry,
    entrada_de_guia,
    parsear_sitemap,
    politica_de_sitio,
    url_de_item,
    url_de_sitio_valida,
)
from zascarr.services.reading_orders.continuity_guide import ContinuityGuideExtractor

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
    "ContinuityGuideExtractor",
    "ExtractorGuias",
    "GuiaLeida",
    "GuiaResumen",
    "RawReadingEntry",
    "ReadingOrdersExtractor",
    "entrada_de_guia",
    "parsear_sitemap",
    "politica_de_sitio",
    "url_de_item",
    "url_de_sitio_valida",
]
