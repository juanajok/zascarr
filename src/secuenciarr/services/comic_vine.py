"""
Cliente Comic Vine API.

Rate limit: 1 req/s (ToS). Respuestas cacheadas en Redis 24h.
Documentación: https://comicvine.gamespot.com/api/documentation
"""
import asyncio
from dataclasses import dataclass
from typing import Any
import httpx, structlog
from secuenciarr.config import get_settings

logger = structlog.get_logger()


@dataclass
class CVResult:
    cv_id: int
    name: str
    description: str | None = None
    image_url: str | None = None
    start_year: int | None = None
    count_of_issues: int | None = None
    raw: dict | None = None


class ComicVineClient:
    BASE_URL = "https://comicvine.gamespot.com/api"

    def __init__(self):
        s = get_settings()
        self._api_key = s.comicvine_api_key
        self._rate_limit = s.comicvine_rate_limit
        self._last_req: float = 0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL, timeout=30.0,
            headers={"User-Agent": "SecuenciArr/0.1"})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _get(self, endpoint: str, params: dict) -> dict:
        now = asyncio.get_event_loop().time()
        if (elapsed := now - self._last_req) < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        params["api_key"] = self._api_key
        params["format"] = "json"
        assert self._client is not None
        r = await self._client.get(endpoint, params=params)
        self._last_req = asyncio.get_event_loop().time()
        r.raise_for_status()
        data = r.json()
        if data.get("error") != "OK":
            logger.warning("comicvine.api_error", error=data.get("error"))
        return data

    async def search_series(self, query: str, limit: int = 10) -> list[CVResult]:
        data = await self._get("/search/", {
            "query": query, "resources": "volume", "limit": limit,
            "field_list": "id,name,description,image,start_year,count_of_issues",
        })
        return [CVResult(
            cv_id=item["id"], name=item.get("name", ""),
            description=item.get("description"),
            image_url=item.get("image", {}).get("medium_url"),
            start_year=_safe_int(item.get("start_year")),
            count_of_issues=item.get("count_of_issues"),
            raw=item,
        ) for item in data.get("results", [])]

    async def get_issue_detail(self, issue_id: int) -> dict[str, Any]:
        data = await self._get(f"/issue/4000-{issue_id}/", {
            "field_list": "id,name,issue_number,volume,description,cover_date,image,person_credits,character_credits,story_arc_credits",
        })
        return data.get("results", {})


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
