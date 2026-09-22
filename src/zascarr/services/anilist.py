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

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx, structlog
from zascarr.config import get_settings

logger = structlog.get_logger()

_MAX_RETRIES = 3
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
    raw: dict | None = None


class AniListClient:
    def __init__(self):
        s = get_settings()
        self._rate_limit = s.anilist_rate_limit
        self._last_req: float = 0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            timeout=30.0, headers={"User-Agent": "ZascArr/0.1"})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _post(self, query: str, variables: dict) -> dict:
        assert self._client is not None

        for attempt in range(_MAX_RETRIES):
            now = asyncio.get_event_loop().time()
            if (elapsed := now - self._last_req) < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            r = await self._client.post(_ENDPOINT, json={"query": query, "variables": variables})
            self._last_req = asyncio.get_event_loop().time()

            if r.status_code == 429:
                retry_after = float(r.headers.get("Retry-After", 2 ** attempt * 2))
                logger.warning("anilist.rate_limited", attempt=attempt, retry_after=retry_after)
                await asyncio.sleep(retry_after)
                continue

            r.raise_for_status()
            data = r.json()
            if "errors" in data:
                logger.warning("anilist.api_error", errors=data["errors"])
            return data

        raise RuntimeError("AniList: rate limit persistente tras reintentos")

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
        description=item.get("description"),
        cover_url=(item.get("coverImage") or {}).get("large"),
        start_year=(item.get("startDate") or {}).get("year"),
        chapters=item.get("chapters"),
        volumes=item.get("volumes"),
        raw=item,
    )
