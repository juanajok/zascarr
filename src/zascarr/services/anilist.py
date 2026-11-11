"""
Cliente AniList (GraphQL) — fuente del enricher para manga/manhwa/manhua.

Comic Vine indexa mal (o nada) estas tradiciones; AniList es la referencia
de facto para ellas y, a diferencia de GCD/Tebeosfera, tiene API pública
sin necesidad de scraping ni API key.

Alcance deliberado: solo enriquece a nivel de SERIE (título, sinopsis,
portada, número de capítulos). AniList no tiene un concepto de "issue"
equivalente al de Comic Vine — sus datos de autoría/staff son de serie
completa, no por capítulo — así que el enricher no intenta usar esta
fuente para Issue.metadata_source individual (ver enricher.py).

Rate limit: AniList ha tenido temporadas en modo degradado (30 req/min en
vez de los 90 habituales); el intervalo por defecto es conservador y,
como el cliente de Comic Vine, respeta Retry-After en 429.
Documentación: https://docs.anilist.co/guide/graphql/
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import httpx
import structlog

from zascarr.config import get_settings
from zascarr.utils.cortesia import PoliticaFuente, politica_de
from zascarr.utils.peticiones import pedir_con_cortesia

# Bug real (reportado, visible en /ui/descubrir): "description(asHtml:
# false)" en la query de más abajo NO quita los "<br>" — AniList los deja
# tal cual en su modo de texto plano, y Jinja2 los escapa a "&lt;br&gt;"
# literal en vez de un salto de línea. Se limpia una vez aquí, en el
# origen, no en cada plantilla que muestre la sinopsis.
_BR_PATTERN = re.compile(r"<br\s*/?>", re.IGNORECASE)

logger = structlog.get_logger()

_ENDPOINT = "https://graphql.anilist.co"

_SEARCH_QUERY = """
query ($search: String, $perPage: Int) {
  Page(perPage: $perPage) {
    media(search: $search, type: MANGA) {
      id
      title { romaji english }
      description(asHtml: false)
      coverImage { large }
      startDate { year }
      chapters
      volumes
      genres
      characters { nodes { name { full } } }
    }
  }
}
"""


@dataclass
class AniListResult:
    anilist_id: int
    title_romaji: str | None = None
    title_english: str | None = None
    description: str | None = None
    cover_url: str | None = None
    start_year: int | None = None
    chapters: int | None = None
    volumes: int | None = None
    genres: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    site_url: str | None = None
    raw: dict | None = None


class AniListClient:
    def __init__(self, *, espera_max_s: float = 30.0,
                 politica: PoliticaFuente | None = None):
        """Sin cadencia propia: la cortesía la comparte todo el proceso (#134)."""
        s = get_settings()
        self._politica = politica or politica_de("anilist", s)
        self._espera_max_s = espera_max_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0, follow_redirects=False,
            headers={"User-Agent": "ZascArr/0.1"})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _post(self, query: str, variables: dict) -> dict:
        if self._client is None:
            raise RuntimeError("Cliente de AniList sin abrir: úsalo con `async with`.")
        r = await pedir_con_cortesia(
            self._client, "POST", _ENDPOINT,
            politica=self._politica, espera_max_s=self._espera_max_s,
            datos={"query": query, "variables": variables},
        )
        data = r.json()
        if "errors" in data:
            logger.warning("anilist.api_error", errors=data["errors"])
        return data

    async def search_manga(self, query: str, limit: int = 10) -> list[AniListResult]:
        data = await self._post(_SEARCH_QUERY, {"search": query, "perPage": limit})
        media = ((data.get("data") or {}).get("Page") or {}).get("media") or []
        return [_parse_media(m) for m in media]


def _parse_media(item: dict) -> AniListResult:
    title = item.get("title") or {}
    return AniListResult(
        anilist_id=item["id"],
        title_romaji=title.get("romaji"),
        title_english=title.get("english"),
        description=_clean_description(item.get("description")),
        cover_url=(item.get("coverImage") or {}).get("large"),
        start_year=(item.get("startDate") or {}).get("year"),
        chapters=item.get("chapters"),
        volumes=item.get("volumes"),
        genres=_textos(item.get("genres")),
        characters=_nombres_de_personajes(item.get("characters")),
        site_url=f"https://anilist.co/manga/{item['id']}",
        raw=item,
    )


def _textos(valor) -> list[str]:
    salida: list[str] = []
    vistos: set[str] = set()
    for texto in valor or []:
        limpio = str(texto or "").strip()
        if limpio and limpio.casefold() not in vistos:
            vistos.add(limpio.casefold())
            salida.append(limpio)
    return salida


def _nombres_de_personajes(valor) -> list[str]:
    nodos = ((valor or {}).get("nodes") or []) if isinstance(valor, dict) else []
    return _textos([(n.get("name") or {}).get("full") for n in nodos if isinstance(n, dict)])


def _clean_description(text: str | None) -> str | None:
    if not text:
        return text
    return _BR_PATTERN.sub("\n", text).strip()
