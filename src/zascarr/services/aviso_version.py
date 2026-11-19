"""Aviso observacional de versión, sin comandos Git ni acciones de actualización."""
from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Callable
from typing import Literal

import httpx

from zascarr.config import get_settings

Estado = Literal["desconocida", "comprobando", "actualizada", "disponible"]
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_URL = "https://api.github.com/repos/juanajok/zascarr/compare/"
_MAX_BODY = 512_000
_TTL_OK = 900
_TTL_ERROR = 60
_PLAZO_TOTAL = 4.0


async def comparar_main(sha: str, client: httpx.AsyncClient) -> Estado:
    """Solo «disponible» si GitHub acredita que main desciende del SHA instalado."""
    if not _SHA.fullmatch(sha):
        return "desconocida"
    try:
        async with client.stream(
            "GET",
            f"{_URL}{sha}...main?per_page=1",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ZascArr-aviso-version",
            },
        ) as response:
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > _MAX_BODY:
                    return "desconocida"
        data = json.loads(body)
        if not isinstance(data, dict):
            return "desconocida"
        base = data["base_commit"]["sha"]
        merge = data["merge_base_commit"]["sha"]
        ahead = data["ahead_by"]
        behind = data["behind_by"]
        if base != sha or merge != sha:
            return "desconocida"
        if type(ahead) is not int or type(behind) is not int or behind != 0:
            return "desconocida"
        if data["status"] == "identical" and ahead == 0:
            return "actualizada"
        if data["status"] == "ahead" and ahead > 0:
            return "disponible"
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        pass
    return "desconocida"


async def consultar_main(sha: str) -> Estado:
    """Consulta fija, sin redirecciones ni proxies del entorno; plazo corto."""
    timeout = httpx.Timeout(3.0, connect=1.5)
    try:
        async with asyncio.timeout(_PLAZO_TOTAL):
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=False, trust_env=False,
            ) as client:
                return await comparar_main(sha, client)
    except TimeoutError:
        return "desconocida"


class AvisoVersion:
    """Caché de proceso con una sola consulta en vuelo; /estado nunca espera a GitHub."""

    def __init__(self, settings: Callable = get_settings) -> None:
        self._settings = settings
        self._sha: str | None = None
        self._value: Estado = "desconocida"
        self._until = 0.0
        self._task: asyncio.Task[None] | None = None

    def estado(self) -> Estado:
        sha = self._settings().build_sha
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            return "desconocida"
        if sha != self._sha:
            self._sha = sha
            self._value = "desconocida"
            self._until = 0.0
        if time.monotonic() >= self._until:
            self._value = "comprobando"
            if self._task is None or self._task.done():
                self._task = asyncio.create_task(self._refresh(sha))
        return self._value

    async def _refresh(self, sha: str) -> None:
        try:
            value = await consultar_main(sha)
        except Exception:  # noqa: BLE001 — fallo externo: siempre desconocido
            value = "desconocida"
        if sha == self._sha:
            self._value = value
            self._until = time.monotonic() + (_TTL_ERROR if value == "desconocida" else _TTL_OK)


aviso_version = AvisoVersion()
