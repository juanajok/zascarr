"""
Cliente Grand Comics Database (GCD) — API REST pública, sin clave.

Verificado en vivo el 2026-09-25 (docs/adr/0002-enricher-scope.md,
actualización): a diferencia de cuando se escribió ese ADR, GCD SÍ tiene
una API pública en https://www.comics.org/api/, anónima, documentada
(Redoc/Swagger). A diferencia del resto de la web de GCD (detrás de un
challenge Cloudflare), el propio /api/ está exento — señal de que es
acceso programático intencional, no scraping a ciegas.

Datos bajo CC BY-SA 4.0: exige atribución + enlace de vuelta, que es
justo lo que ya hace /ui/descubrir con las otras tres fuentes (ver
DiscoveryResult.site_url).

Alcance deliberado, solo para C0 (descubrir y dar de alta una Series):
la API de búsqueda por nombre NO trae sinopsis ni portada a nivel de
serie (solo editorial, idioma, formato físico, lista de números) — no
sirve para el enricher (B4), que sigue cerrado con Comic Vine/AniList/
Tebeosfera tal cual (ver ADR-0002).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx
import structlog

from zascarr.config import get_settings

logger = structlog.get_logger()

_BASE_URL = "https://www.comics.org/api"

# GCD indexa por país/idioma, no por una "tradición" ZascArr — mapeo
# best-effort para preseleccionar algo razonable en el formulario de alta;
# el coleccionista lo corrige antes de confirmar (mismo criterio que las
# otras tres fuentes, ver DiscoveryResult.tradition_guess).
_LANGUAGE_TRADITION = {
    "en": "american",
    "fr": "franco_belgian",
    "es": "tebeo",
    "ja": "manga",
    "ko": "manhwa",
    "zh": "manhua",
    "it": "fumetti",
}
_BRITISH_COUNTRIES = {"gb", "uk"}


@dataclass
class GCDResult:
    gcd_id: int
    name: str
    year_began: int | None = None
    year_ended: int | None = None
    language: str | None = None
    country: str | None = None
    site_url: str | None = None
    raw: dict | None = None

    @property
    def tradition_guess(self) -> str:
        if (self.country or "").lower() in _BRITISH_COUNTRIES:
            return "british"
        return _LANGUAGE_TRADITION.get((self.language or "").lower(), "other")


class GCDClient:
    def __init__(self):
        s = get_settings()
        self._rate_limit = s.gcd_rate_limit
        self._last_req: float = 0
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL, timeout=30.0,
            headers={
                "User-Agent": "ZascArr/0.1 (+https://github.com/juanajok/zascarr)",
                # Bug real (reportado, verificado en vivo): sin este header,
                # Django REST Framework devuelve su interfaz HTML navegable
                # en vez de JSON (negociación de contenido por defecto), y
                # r.json() revienta al intentar parsear HTML.
                "Accept": "application/json",
            })
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_req
        if elapsed < self._rate_limit:
            await asyncio.sleep(self._rate_limit - elapsed)
        self._last_req = time.monotonic()

    async def search_series(self, query: str, limit: int = 10) -> list[GCDResult]:
        query = (query or "").strip()
        if not query:
            return []
        await self._throttle()
        try:
            r = await self._client.get(f"/series/name/{quote(query, safe='')}/")
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPError as exc:
            logger.warning("gcd.request_failed", query=query, error=str(exc))
            return []
        except ValueError as exc:
            # JSON inválido (p.ej. Cloudflare interponiendo una página de
            # verificación en vez de la API): "sin resultado", nunca una
            # excepción que tumbe la búsqueda — mismo criterio que
            # Tebeosfera (services/tebeosfera.py) ante fallos de parseo.
            logger.warning("gcd.invalid_json", query=query, error=str(exc))
            return []
        results = []
        for item in data.get("results", [])[:limit]:
            gcd_id = _id_from_api_url(item.get("api_url", ""))
            if gcd_id is None:
                continue
            results.append(GCDResult(
                gcd_id=gcd_id, name=item.get("name", ""),
                year_began=item.get("year_began"), year_ended=item.get("year_ended"),
                language=item.get("language"), country=item.get("country"),
                site_url=f"https://www.comics.org/series/{gcd_id}/",
                raw=item,
            ))
        return results


def _id_from_api_url(api_url: str) -> int | None:
    """".../api/series/64252/" -> 64252"""
    parts = [p for p in api_url.rstrip("/").split("/") if p]
    return int(parts[-1]) if parts and parts[-1].isdigit() else None
