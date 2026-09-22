"""
Cliente Comic Vine API.

Rate limit: 1 req/s (ToS). Respuestas cacheadas en Redis 24h.
Documentación: https://comicvine.gamespot.com/api/documentation
"""
import asyncio
from dataclasses import dataclass, field
from typing import Any
import httpx, structlog
from zascarr.config import get_settings

logger = structlog.get_logger()

_MAX_RETRIES = 3


@dataclass
class CVResult:
    cv_id: int
    name: str
    description: str | None = None
    image_url: str | None = None
    start_year: int | None = None
    count_of_issues: int | None = None
    raw: dict | None = None


@dataclass
class CVCredit:
    """Un creador citado en person_credits, con uno o más roles.

    Comic Vine devuelve el rol como texto libre y a veces varios separados
    por coma ("writer, plotter"): se guardan todos tal cual, sin adivinar.
    El mapeo a CreatorRole es responsabilidad del enricher, no del cliente.
    """
    cv_id: int | None
    name: str
    roles: list[str] = field(default_factory=list)


@dataclass
class CVIssueResult:
    cv_id: int
    issue_number: str | None = None
    description: str | None = None
    image_url: str | None = None
    cover_date: str | None = None
    credits: list[CVCredit] = field(default_factory=list)
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
            headers={"User-Agent": "ZascArr/0.1"})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _get(self, endpoint: str, params: dict) -> dict:
        # No mutar el dict del caller: params["api_key"] = ... antes escribía
        # en el diccionario que pasó quien llamó, un efecto secundario
        # invisible detectado en el peer review.
        request_params = {**params, "api_key": self._api_key, "format": "json"}
        assert self._client is not None

        for attempt in range(_MAX_RETRIES):
            now = asyncio.get_event_loop().time()
            if (elapsed := now - self._last_req) < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            r = await self._client.get(endpoint, params=request_params)
            self._last_req = asyncio.get_event_loop().time()

            if r.status_code == 429:
                retry_after = float(r.headers.get("Retry-After", 2 ** attempt * 2))
                logger.warning("comicvine.rate_limited",
                               attempt=attempt, retry_after=retry_after)
                await asyncio.sleep(retry_after)
                continue

            r.raise_for_status()
            data = r.json()
            if data.get("error") != "OK":
                logger.warning("comicvine.api_error", error=data.get("error"))
            return data

        raise RuntimeError("Comic Vine: rate limit persistente tras reintentos")

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

    async def find_issue(self, volume_id: int, issue_number: str) -> CVIssueResult | None:
        """Busca un número concreto dentro de un volumen ya conocido.

        Es la pieza que faltaba para el enricher: dado un volume_id (el
        comic_vine_id de una Series ya resuelta) y un issue_number, resuelve
        el issue exacto sin tener que adivinar su ID de Comic Vine.
        """
        data = await self._get("/issues/", {
            "filter": f"volume:{volume_id},issue_number:{issue_number}",
            "field_list": "id,issue_number,description,image,cover_date,person_credits",
            "limit": 1,
        })
        results = data.get("results", [])
        if not results:
            return None
        return _parse_issue(results[0])


def _parse_issue(item: dict) -> CVIssueResult:
    credits = []
    for pc in item.get("person_credits", []) or []:
        roles = [r.strip().lower() for r in (pc.get("role") or "").split(",") if r.strip()]
        if pc.get("name"):
            credits.append(CVCredit(cv_id=pc.get("id"), name=pc["name"], roles=roles))
    return CVIssueResult(
        cv_id=item["id"],
        issue_number=item.get("issue_number"),
        description=item.get("description"),
        image_url=(item.get("image") or {}).get("medium_url"),
        cover_date=item.get("cover_date"),
        credits=credits,
        raw=item,
    )


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
