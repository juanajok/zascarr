"""Cliente Transmission JSON-RPC."""
import httpx
import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()


class TransmissionClient:
    def __init__(self):
        s = get_settings()
        self._rpc_url = f"{s.transmission_url}/transmission/rpc"
        self._auth = (s.transmission_username, s.transmission_password) if s.transmission_username else None
        self._session_id = ""

    async def _rpc(self, method: str, arguments: dict | None = None) -> dict:
        payload = {"method": method}
        if arguments:
            payload["arguments"] = arguments
        async with httpx.AsyncClient(timeout=30.0) as client:
            for _ in range(2):
                headers = {}
                if self._session_id:
                    headers["X-Transmission-Session-Id"] = self._session_id
                r = await client.post(self._rpc_url, json=payload, auth=self._auth, headers=headers)
                if r.status_code == 409:
                    self._session_id = r.headers.get("X-Transmission-Session-Id", "")
                    continue
                r.raise_for_status()
                return r.json()
        return {"result": "error", "arguments": {}}

    async def add_torrent(self, url: str, download_dir: str | None = None) -> dict | None:
        s = get_settings()
        args = {"filename": url, "download-dir": download_dir or s.transmission_download_dir, "paused": False}
        data = await self._rpc("torrent-add", args)
        added = data.get("arguments", {}).get("torrent-added") or data.get("arguments", {}).get("torrent-duplicate")
        if added:
            logger.info("transmission.added", name=added.get("name", ""))
        return added

    async def list_completed(self, download_dir: str | None = None) -> list[dict]:
        s = get_settings()
        data = await self._rpc("torrent-get", {"fields": ["id","name","hashString","percentDone","downloadDir","totalSize","files"]})
        target = download_dir or s.transmission_download_dir
        return [t for t in data.get("arguments", {}).get("torrents", [])
                if t.get("percentDone", 0) == 1 and target in t.get("downloadDir", "")]

    async def remove_torrent(self, torrent_id: int, delete_data: bool = False) -> bool:
        data = await self._rpc("torrent-remove", {"ids": [torrent_id], "delete-local-data": delete_data})
        return data.get("result") == "success"

    async def get_session_stats(self) -> dict:
        data = await self._rpc("session-stats")
        return data.get("arguments", {})
