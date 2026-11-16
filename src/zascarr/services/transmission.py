"""Cliente Transmission JSON-RPC."""
import httpx
import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()


class TransmissionClient:
    def __init__(self):
        s = get_settings()
        self._rpc_url = f"{s.transmission_url}/transmission/rpc"
        self._auth = (
            (s.transmission_username, s.transmission_password) if s.transmission_username else None
        )
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
        dir_configurado = download_dir or s.transmission_download_dir
        data = await self._rpc("torrent-add", {
            "filename": url,
            "download-dir": dir_configurado,
            "paused": False,
        })
        agregado = data.get("arguments", {}) or {}
        added = agregado.get("torrent-added") or agregado.get("torrent-duplicate")
        if added:
            logger.info("transmission.added", name=added.get("name", ""))
            return added

        # Un «torrent-add» que no devuelve torrent-added ni duplicate es un
        # fallo que antes se perdía en silencio (2026-11-16). El caso habitual
        # es una `download-dir` que no existe en el host: se reintenta con la
        # carpeta por defecto de Transmission, que el importador también ve a
        # través del montaje de descargas, en vez de dejar el deseo colgado.
        logger.warning("transmission.download_dir_invalido",
                       carpeta=dir_configurado,
                       resultado=str(data.get("result"))[:80])
        if dir_configurado:
            data = await self._rpc("torrent-add", {
                "filename": url,
                "paused": False,
            })
            agregado = data.get("arguments", {}) or {}
            added = (agregado.get("torrent-added")
                     or agregado.get("torrent-duplicate"))
            if added:
                logger.info("transmission.added_carpeta_por_defecto",
                            name=added.get("name", ""))
                return added
        logger.warning("transmission.add_failed",
                       resultado=str(data.get("result"))[:80],
                       claves=sorted(agregado.keys())[:10])
        return None

    async def list_torrents(self) -> list[dict]:
        """Todos los torrents con su carpeta y sus archivos (#488: guardián de compartidos).

        No filtra por completados ni por carpeta: un archivo de la biblioteca puede estar en
        cualquier torrent que Transmission conozca (incluido uno aún descargando o sembrando).
        """
        data = await self._rpc(
            "torrent-get",
            {
                "fields": [
                    "id",
                    "name",
                    "hashString",
                    "percentDone",
                    "downloadDir",
                    "totalSize",
                    "files",
                ]
            },
        )
        return list(data.get("arguments", {}).get("torrents", []))

    async def list_completed(self, download_dir: str | None = None) -> list[dict]:
        s = get_settings()
        target = download_dir or s.transmission_download_dir
        return [t for t in await self.list_torrents()
                if t.get("percentDone", 0) == 1 and target in t.get("downloadDir", "")]

    async def remove_torrent(self, torrent_id: int, delete_data: bool = False) -> bool:
        data = await self._rpc(
            "torrent-remove", {"ids": [torrent_id], "delete-local-data": delete_data}
        )
        return data.get("result") == "success"

    async def get_session_stats(self) -> dict:
        data = await self._rpc("session-stats")
        return data.get("arguments", {})
