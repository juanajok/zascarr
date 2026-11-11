"""Cliente Metron — API pública de cómics EN/IT, con token propio de la instalación.

Alcance de esta entrega: **Descubrir** (búsqueda de serie). No enriquece todavía
(mismo corte que GCD, ADR 0002). Datos CC BY-SA 4.0: la UI debe atribuir; las
portadas NO están cubiertas por esa licencia y aquí no se usan.

Verificado en documentación pública (`api/README.md`, v1.12): base
`https://metron.cloud/api/`, token `Authorization: Bearer <token>`, listas
paginadas `{count,next,previous,results}` y límites 20/min · 5.000/día.
No se ha llamado a la API en vivo: eso queda NOT RUN.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote

import httpx
import structlog

from zascarr.config import get_settings
from zascarr.utils.cortesia import CortesiaProceso, PoliticaFuente, politica_de
from zascarr.utils.peticiones import (
    ErrorDePeticion,
    pedir_con_cortesia,
)

logger = structlog.get_logger()

_BASE_URL = "https://metron.cloud/api"
SITIO = "https://metron.cloud"
ATRIBUCION = "Datos de Metron, CC BY-SA 4.0"
USER_AGENT = "ZascArr/0.1 (+https://github.com/juanajok/zascarr)"


@dataclass(frozen=True)
class MetronResult:
    metron_id: int
    name: str
    year_began: int | None = None
    year_ended: int | None = None
    volume: int | None = None
    issue_count: int | None = None
    publisher: str | None = None
    series_type: str | None = None
    language: str | None = None
    descripcion: str | None = None
    site_url: str | None = None
    raw: dict | None = None

    @property
    def tradition_guess(self) -> str | None:
        """Metron declara el idioma; se usa como pista, nunca como identidad."""
        if (self.language or "").lower() == "it":
            return "fumetti"
        if (self.language or "").lower() == "en":
            return "american"
        return None


def _texto(valor: object) -> str | None:
    return str(valor).strip() if valor not in (None, "") else None


def _serie_desde_raw(item: dict) -> MetronResult | None:
    if not isinstance(item, dict):
        return None
    try:
        metron_id = int(item.get("id"))
    except (TypeError, ValueError):
        return None
    publisher = item.get("publisher")
    if isinstance(publisher, dict):
        publisher = publisher.get("name")
    series_type = item.get("series_type")
    if isinstance(series_type, dict):
        series_type = series_type.get("name")
    return MetronResult(
        metron_id=metron_id,
        name=str(item.get("series") or item.get("name") or "").strip(),
        year_began=item.get("year_began"), year_ended=item.get("year_end"),
        volume=item.get("volume"), issue_count=item.get("issue_count"),
        publisher=_texto(publisher), series_type=_texto(series_type),
        language=_texto(item.get("language")),
        descripcion=_texto(item.get("desc")),
        site_url=(item.get("resource_url") or f"{SITIO}/series/{metron_id}/"),
        raw=item,
    )


class MetronClient:
    def __init__(self, *, token: str | None = None,
                 politica: PoliticaFuente | None = None,
                 cortesia: CortesiaProceso | None = None,
                 reloj=time.monotonic, dormir=asyncio.sleep,
                 espera_max_s: float = 30.0,
                 transporte: httpx.AsyncBaseTransport | None = None):
        s = get_settings()
        self._token = (token if token is not None else s.metron_token) or ""
        self._politica = politica or politica_de("metron", s)
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._transporte = transporte
        self._client: httpx.AsyncClient | None = None
        self.ultimas_peticiones = 0

    @property
    def configurado(self) -> bool:
        return bool(self._token.strip())

    async def __aenter__(self):
        if not self.configurado:
            raise RuntimeError("Metron sin token: no se consulta")
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL, timeout=30.0, follow_redirects=False,
            transport=self._transporte,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token.strip()}",
            })
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def search_series(self, query: str, limit: int = 10) -> list[MetronResult]:
        """Una página de `/series/?q=…`; no pagina ni descarga en bloque."""
        query = (query or "").strip()
        self.ultimas_peticiones = 0
        if not query or limit <= 0:
            return []
        if self._client is None:
            raise RuntimeError("Cliente de Metron sin abrir: úsalo con `async with`.")
        self.ultimas_peticiones += 1
        r = await pedir_con_cortesia(
            self._client, "GET", f"{_BASE_URL}/series/?q={quote(query, safe='')}",
            politica=self._politica, espera_max_s=self._espera_max_s,
            cortesia=self._cortesia, reloj=self._reloj, dormir=self._dormir,
        )
        try:
            data = r.json()
        except ValueError as exc:
            raise ErrorDePeticion("respuesta JSON inválida de Metron") from exc
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            raise ErrorDePeticion("respuesta inválida de Metron")
        resultados: list[MetronResult] = []
        for item in data["results"]:
            serie = _serie_desde_raw(item)
            if serie is not None and serie.name:
                resultados.append(serie)
            if len(resultados) >= limit:
                break
        return resultados

    async def get_series(self, metron_id: int) -> MetronResult | None:
        """`GET /series/{id}/` para detalle (no usado aún por el enricher)."""
        if self._client is None:
            raise RuntimeError("Cliente de Metron sin abrir: úsalo con `async with`.")
        if not isinstance(metron_id, int) or metron_id <= 0:
            return None
        self.ultimas_peticiones += 1
        r = await pedir_con_cortesia(
            self._client, "GET", f"{_BASE_URL}/series/{metron_id}/",
            politica=self._politica, espera_max_s=self._espera_max_s,
            cortesia=self._cortesia, reloj=self._reloj, dormir=self._dormir,
        )
        try:
            data = r.json()
        except ValueError:
            logger.warning("metron.get_series_json_invalido", metron_id=metron_id)
            return None
        return _serie_desde_raw(data) if isinstance(data, dict) else None
