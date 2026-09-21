"""Cliente aMule vía amuleweb HTTP."""
import hashlib, re
from urllib.parse import quote
import httpx, structlog
from secuenciarr.config import get_settings

logger = structlog.get_logger()


class AMuleClient:
    def __init__(self):
        s = get_settings()
        self._base = s.amule_url
        self._password = s.amule_password
        self._cookies: dict[str, str] = {}

    async def login(self) -> bool:
        pw_hash = hashlib.md5(self._password.encode()).hexdigest()
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            r = await client.post(f"{self._base}/", data={"p": pw_hash})
            for name, value in r.cookies.items():
                self._cookies[name] = value
            set_cookie = r.headers.get("set-cookie", "")
            if set_cookie and not self._cookies:
                self._cookies["ses"] = set_cookie.split(";")[0].split("=", 1)[-1]
            self._logged_in = bool(self._cookies)
            if self._logged_in:
                logger.info("amule.login_ok")
            return self._logged_in

    async def _get(self, path: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True,
                                     cookies=self._cookies) as client:
            r = await client.get(f"{self._base}{path}")
            r.raise_for_status()
            return r.text

    async def add_ed2k_link(self, link: str) -> bool:
        if not link.startswith("ed2k://"):
            return False
        try:
            await self._get(f"/amuleweb/?ed2k={quote(link, safe=':/|')}")
            logger.info("amule.ed2k_added", link=link[:80])
            return True
        except Exception:
            logger.exception("amule.add_failed")
            return False

    async def list_completed_comics(self) -> list[dict]:
        try:
            html = await self._get("/amuleweb/")
            pattern = re.compile(r'(\d+\.?\d*)\s*%', re.DOTALL)
            results = []
            for m in pattern.finditer(html):
                pct = float(m.group(1))
                if pct >= 100.0:
                    results.append({"percent_done": pct, "completed": True})
            return results
        except Exception:
            return []

    async def get_status(self) -> dict:
        try:
            html = await self._get("/amuleweb/")
            return {"reachable": True, "connected": "connected" in html.lower()}
        except Exception:
            return {"reachable": False, "connected": False}
