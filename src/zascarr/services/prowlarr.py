"""Cliente Prowlarr REST API."""
from dataclasses import dataclass

import httpx
import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()


@dataclass
class SearchResult:
    title: str
    indexer: str
    download_url: str
    size_bytes: int
    seeders: int
    category: str
    publish_date: str | None = None


class ProwlarrClient:
    def __init__(self):
        s = get_settings()
        self._base = s.prowlarr_url
        self._api_key = s.prowlarr_api_key

    async def search(self, query: str, categories: list[int] | None = None) -> list[SearchResult]:
        if not self._api_key:
            logger.warning("prowlarr.no_api_key")
            return []
        params: dict = {"query": query, "type": "search"}
        if categories:
            params["categories"] = categories
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{self._base}/api/v1/search", params=params,
                                 headers={"X-Api-Key": self._api_key})
            r.raise_for_status()
            data = r.json()
        results = [SearchResult(
            title=item.get("title", ""),
            indexer=item.get("indexer", ""),
            download_url=item.get("downloadUrl", ""),
            size_bytes=item.get("size", 0),
            seeders=item.get("seeders", 0),
            category=str(item.get("categories", [{}])[0].get("name", "")),
            publish_date=item.get("publishDate"),
        ) for item in data]
        results.sort(key=lambda r: r.seeders, reverse=True)
        return results
