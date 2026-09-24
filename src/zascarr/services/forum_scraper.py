"""Scraper de foros IPB (plugin genérico; la URL la aporta el usuario). Rate limit: 2s mínimo."""
import asyncio
import re
from dataclasses import dataclass, field
from urllib.parse import quote, urljoin

import httpx
import structlog

logger = structlog.get_logger()

ED2K_PATTERN   = re.compile(r'ed2k://\|file\|[^"<\s]+', re.IGNORECASE)
MAGNET_PATTERN = re.compile(r'magnet:\?xt=urn:[^"<\s]+', re.IGNORECASE)
TOPIC_PATTERN  = re.compile(r'<a[^>]+href=["\']([^"\']*showtopic=\d+)["\'][^>]*>([^<]+)</a>', re.IGNORECASE)


@dataclass
class ForumResult:
    topic_title: str
    topic_url: str
    ed2k_links: list[str] = field(default_factory=list)
    magnet_links: list[str] = field(default_factory=list)


class ForumScraper:
    def __init__(self, base_url: str, rate_limit: float = 2.0):
        self._base = base_url.rstrip("/")
        self._rate_limit = rate_limit
        self._last_req: float = 0
        self._cookies: dict = {}

    async def login(self, username: str, password: str) -> bool:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            r = await client.post(f"{self._base}/index.php?act=Login&CODE=01",
                                  data={"UserName": username, "PassWord": password, "CookieDate": "1"})
            for k, v in r.cookies.items():
                self._cookies[k] = v
            self._logged_in = bool(self._cookies) and r.status_code in (200, 301, 302)
            return self._logged_in

    async def _get(self, url: str) -> str:
        now = asyncio.get_event_loop().time()
        if (elapsed := now - self._last_req) < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, cookies=self._cookies,
                                     headers={"User-Agent": "ZascArr/0.1"}) as client:
            r = await client.get(url)
            self._last_req = asyncio.get_event_loop().time()
            r.raise_for_status()
            return r.text

    async def use_ipb_search(self, query: str) -> list[ForumResult]:
        try:
            html = await self._get(
                f"{self._base}/index.php?act=Search&CODE=01&keywords={quote(query)}&searchin=titles"
            )
        except Exception:
            logger.exception("forum.search_failed", query=query)
            return []
        results = []
        for href, title in TOPIC_PATTERN.findall(html)[:10]:
            url = urljoin(self._base + "/", href)
            try:
                topic_html = await self._get(url)
                ed2k    = list(dict.fromkeys(ED2K_PATTERN.findall(topic_html)))
                magnets = list(dict.fromkeys(MAGNET_PATTERN.findall(topic_html)))
                if ed2k or magnets:
                    results.append(ForumResult(title.strip(), url, ed2k, magnets))
            except Exception:
                logger.exception("forum.topic_failed", url=url)
        return results
