"""
Orquestador — motor de búsqueda en cascada.

Flujo: wishlist (wanted) → Prowlarr → foro CRG → Transmission/aMule
Backend auto-detectado por tipo de URL:
  magnet:// o .torrent → Transmission
  ed2k://              → aMule
"""
from enum import Enum
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from secuenciarr.models import Issue, Series, Wishlist, WishlistStatus
from secuenciarr.services.amule import AMuleClient
from secuenciarr.services.prowlarr import ProwlarrClient, SearchResult
from secuenciarr.services.transmission import TransmissionClient
from secuenciarr.utils.naming import normalize_series_name

logger = structlog.get_logger()

COMIC_CATEGORIES = [7030, 7020]
MAX_SIZE_BYTES = 500 * 1024 * 1024


class DownloadBackend(str, Enum):
    TRANSMISSION = "transmission"
    AMULE        = "amule"


def _detect_backend(url: str) -> DownloadBackend:
    return DownloadBackend.AMULE if url.lower().startswith("ed2k://") else DownloadBackend.TRANSMISSION


class Orchestrator:
    def __init__(self, db: AsyncSession):
        self.db = db
        self._prowlarr     = ProwlarrClient()
        self._transmission = TransmissionClient()
        self._amule        = AMuleClient()

    async def process_wishlist(self, limit: int = 10) -> int:
        items = list((await self.db.execute(
            select(Wishlist)
            .where(Wishlist.status == WishlistStatus.WANTED)
            .order_by(Wishlist.priority.asc(), Wishlist.added_at.asc())
            .limit(limit)
        )).scalars().all())

        sent = 0
        for item in items:
            try:
                if await self._process_item(item):
                    sent += 1
            except Exception:
                logger.exception("orchestrator.item_failed", id=str(item.id))
                item.status = WishlistStatus.FAILED
                await self.db.flush()
        return sent

    async def _process_item(self, item: Wishlist) -> bool:
        query = await self._build_query(item)
        if not query:
            return False

        item.status = WishlistStatus.SEARCHING
        await self.db.flush()

        results = await self._prowlarr.search(query, categories=COMIC_CATEGORIES)
        best = self._select_best(results, query) if results else None

        if not best:
            best = await self._forum_fallback(query)

        if not best:
            item.status = WishlistStatus.WANTED
            await self.db.flush()
            return False

        backend = _detect_backend(best.download_url)
        success = await self._send(backend, best)

        if success:
            item.status = WishlistStatus.DOWNLOADING
            from datetime import datetime, timezone
            item.last_searched_at = datetime.now(timezone.utc)
            logger.info("orchestrator.download_started", title=best.title, backend=backend.value)
        else:
            item.status = WishlistStatus.FAILED
        await self.db.flush()
        return success

    async def _build_query(self, item: Wishlist) -> str | None:
        if item.search_query:
            return item.search_query
        if item.series_id:
            series = (await self.db.execute(select(Series).where(Series.id == item.series_id))).scalar_one_or_none()
            if not series:
                return None
            q = series.title
            if item.issue_id:
                issue = (await self.db.execute(select(Issue).where(Issue.id == item.issue_id))).scalar_one_or_none()
                if issue and issue.issue_number:
                    q += f" {issue.issue_number}"
            return q
        if item.issue_id:
            issue = (await self.db.execute(select(Issue).where(Issue.id == item.issue_id))).scalar_one_or_none()
            if issue:
                series = (await self.db.execute(select(Series).where(Series.id == issue.series_id))).scalar_one_or_none()
                if series:
                    return f"{series.title} {issue.issue_number}"
        return None

    async def _send(self, backend: DownloadBackend, result: SearchResult) -> bool:
        if backend == DownloadBackend.TRANSMISSION:
            return (await self._transmission.add_torrent(result.download_url)) is not None
        if backend == DownloadBackend.AMULE:
            if not await self._amule.login():
                return False
            return await self._amule.add_ed2k_link(result.download_url)
        return False

    async def _forum_fallback(self, query: str) -> SearchResult | None:
        from secuenciarr.config import get_settings
        s = get_settings()
        if not s.forum_enabled or not s.forum_username:
            return None
        try:
            from secuenciarr.services.forum_scraper import ForumScraper
            scraper = ForumScraper(base_url=s.forum_url, rate_limit=s.forum_rate_limit)
            await scraper.login(s.forum_username, s.forum_password)
            for fr in await scraper.use_ipb_search(query):
                if fr.ed2k_links:
                    return SearchResult(fr.topic_title, "forum:crg", fr.ed2k_links[0], 0, 0, "comics")
                if fr.magnet_links:
                    return SearchResult(fr.topic_title, "forum:crg", fr.magnet_links[0], 0, 1, "comics")
        except Exception:
            logger.exception("orchestrator.forum_fallback_error")
        return None

    def _select_best(self, results: list[SearchResult], query: str) -> SearchResult | None:
        norm = normalize_series_name(query)
        torrents, ed2k = [], []
        for r in results:
            if r.size_bytes > MAX_SIZE_BYTES:
                continue
            backend = _detect_backend(r.download_url)
            score = self._score(r, norm)
            if backend == DownloadBackend.TRANSMISSION:
                if r.seeders >= 1:
                    torrents.append((score, r))
            else:
                ed2k.append((score, r))
        for pool in (torrents, ed2k):
            if pool:
                pool.sort(key=lambda x: x[0], reverse=True)
                return pool[0][1]
        return None

    @staticmethod
    def _score(r: SearchResult, norm: str) -> float:
        t = normalize_series_name(r.title)
        title_score = 1.0 if norm in t else (0.6 if any(w in t for w in norm.split()) else 0.2)
        if any(m in t for m in ["variant", "2nd print", "reprint", "sketch"]):
            title_score *= 0.3
        seeder_score = min(r.seeders / 50, 1.0) if r.seeders > 0 else 0.1
        fmt = 1.0 if ".cbz" in r.title.lower() else (0.8 if ".cbr" in r.title.lower() else 0.5)
        return title_score * 0.6 + seeder_score * 0.3 + fmt * 0.1
