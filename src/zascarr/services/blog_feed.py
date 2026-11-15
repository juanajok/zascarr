"""Conector genérico para blogs/RSS configurados por el usuario (BLOG1).

No conoce ningún sitio concreto y no scrapea posts: solo acepta enlaces de
descarga directa que ya vengan en el feed (magnet o ed2k).
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
import structlog

from zascarr.services.prowlarr import SearchResult
from zascarr.utils.url_portada import analizar_url, descargar_publico

logger = structlog.get_logger()

MAX_CUERPO_FEED = 4 * 1024 * 1024
MAX_DESCARGA_URL = 2048
MAX_TITULO = 500
_MAGNET = re.compile(r"magnet:\?[^\s\"'<>]+", re.IGNORECASE)
_ED2K = re.compile(r"ed2k://[^\s\"'<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class EntradaFeed:
    titulo: str
    enlace: str
    publicado: str | None
    descarga_url: str | None
    tipo: str | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _texto(elemento: ET.Element | None) -> str:
    return (elemento.text or "").strip() if elemento is not None else ""


def _url_segura(url: str | None) -> str | None:
    """Solo enlaces de descarga directa: magnet o ed2k. Nada de http(s) de páginas."""
    if not url:
        return None
    limpia = url.strip()
    if not limpia or len(limpia) > MAX_DESCARGA_URL:
        return None
    bajo = limpia.lower()
    if bajo.startswith("magnet:"):
        return limpia if "xt=urn:btih:" in bajo and _MAGNET.fullmatch(limpia) else None
    if bajo.startswith("ed2k://"):
        return limpia if _ED2K.fullmatch(limpia) and "|file|" in bajo else None
    return None


def _descarga_en(texto: str) -> tuple[str | None, str | None]:
    """Primer enlace directo del texto: magnet o ed2k."""
    if not texto:
        return None, None
    for patron, tipo in ((_MAGNET, "magnet"), (_ED2K, "ed2k")):
        m = patron.search(texto)
        if m:
            candidato = _url_segura(m.group(0))
            if candidato:
                return candidato, tipo
    return None, None


def _enlace_de(entrada: ET.Element) -> str:
    for hijo in entrada.iter():
        if _local(hijo.tag) != "link":
            continue
        href = (hijo.get("href") or "").strip()
        if href:
            rel = (hijo.get("rel") or "alternate").lower()
            if rel == "alternate":
                return href
        if _texto(hijo):
            return _texto(hijo)
    return ""


def _entradas(xml_texto: str | bytes) -> list[ET.Element]:
    try:
        # `xml.etree` no resuelve entidades externas y expat >= 2.4.1 corta las anidadas;
        # el cuerpo está acotado por `MAX_CUERPO_FEED`. Mismo criterio que ComicInfo.
        raiz = ET.fromstring(xml_texto)  # noqa: S314
    except ET.ParseError:
        logger.warning("blog_feed.xml_invalido")
        return []
    nombre = _local(raiz.tag)
    if nombre == "rss":
        return [e for e in raiz.iter() if _local(e.tag) == "item"]
    if nombre == "feed":
        return [e for e in raiz.iter() if _local(e.tag) == "entry"]
    logger.warning("blog_feed.formato_desconocido", raiz=nombre)
    return []


def parsear_feed(xml_texto: str | bytes) -> list[EntradaFeed]:
    """Parsea RSS 2.0 o Atom; XML inválido devuelve [] y se registra."""
    salida: list[EntradaFeed] = []
    for entrada in _entradas(xml_texto):
        titulo = ""
        enlace = ""
        publicado = None
        descarga: str | None = None
        tipo: str | None = None
        for hijo in entrada.iter():
            nombre = _local(hijo.tag)
            if nombre == "title" and not titulo:
                titulo = _texto(hijo)
            elif nombre in ("pubdate", "published", "updated", "date") and not publicado:
                publicado = _texto(hijo) or None
            elif nombre == "enclosure":
                candidato = _url_segura(hijo.get("url"))
                if candidato and descarga is None:
                    bajo = candidato.lower()
                    if bajo.startswith("magnet:"):
                        descarga, tipo = candidato, "magnet"
                    elif bajo.startswith("ed2k://"):
                        descarga, tipo = candidato, "ed2k"
            elif nombre in ("link", "description", "content", "encoded", "summary"):
                candidato, tipo_candidato = _descarga_en(_texto(hijo))
                if candidato and descarga is None:
                    descarga, tipo = candidato, tipo_candidato
            elif hijo.get("url") or hijo.get("href"):
                candidato, tipo_candidato = _descarga_en(
                    hijo.get("url") or hijo.get("href") or "")
                if candidato and descarga is None:
                    descarga, tipo = candidato, tipo_candidato
        enlace = _enlace_de(entrada).strip()[:MAX_DESCARGA_URL]
        titulo = titulo.strip()[:MAX_TITULO]
        if not titulo:
            continue
        if descarga is None:
            continue  # solo posts del blog: no se scrapea ni se inventa
        salida.append(EntradaFeed(
            titulo=titulo, enlace=enlace,
            publicado=publicado[:100] if publicado else None,
            descarga_url=descarga, tipo=tipo))
    return salida


def _relevante(titulo: str, consulta: str, alias: set[str] | None = None) -> bool:
    from zascarr.core.matcher import normalize_title
    from zascarr.utils.naming import normalize_series_name

    terminos = [t for t in normalize_series_name(consulta).split() if len(t) > 1]
    if not terminos:
        return True
    normalizado = normalize_series_name(titulo)
    if alias and normalize_title(titulo) in alias:
        return True
    return all(t in normalizado for t in terminos)


async def _descargar(url: str, _cliente=None, _cache=None, _robots=None) -> bytes:
    return await descargar_publico(url, max_bytes=MAX_CUERPO_FEED)




async def buscar_en_feed(
    url: str, consulta: str, cliente: httpx.AsyncClient | None = None,
    cache=None, robots=None, *, alias: set[str] | None = None,
) -> list[EntradaFeed]:
    """Descarga y filtra entradas con enlace directo y todos los términos."""
    from zascarr.utils.cortesia import fuente_habilitada

    if not estado_feed(url) or not fuente_habilitada("blog"):
        return []
    try:
        xml_texto = await _descargar(url, cliente)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("blog_feed.lectura_fallida", url=url, motivo=type(exc).__name__)
        return []
    if not xml_texto:
        return []
    return [e for e in parsear_feed(xml_texto)
            if _relevante(e.titulo, consulta, alias)]


def estado_feed(url: str) -> bool:
    """URL http(s) válida; la comprobación de fuente encendida la hace la caché/orquestador."""
    if not url:
        return False
    try:
        analizar_url(url, exigir_lista=False)
    except ValueError:
        return False
    return True


def resultados_de_busqueda(entradas: list[EntradaFeed], url: str) -> list[SearchResult]:
    """Convierte entradas a `SearchResult` directos para el orquestador."""
    host = urlsplit(url).hostname or "blog"
    return [SearchResult(
        title=e.titulo, indexer=f"blog:{host}", download_url=e.descarga_url or "",
        size_bytes=0, seeders=0, category="blog", publish_date=e.publicado,
    ) for e in entradas if e.descarga_url]


