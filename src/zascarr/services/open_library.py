"""Cliente Open Library — obras/tomos, sin clave y con User-Agent identificado.

Alcance de esta entrega: **Descubrir** (búsqueda de obra/tomo). Open Library no
indexa grapas; no se usa para ISBN como identificador de serie (BL-R5) ni para el
enricher todavía. La API pide caché y no uso masivo: aquí solo se pide al buscar,
sin dumps.

Verificado en documentación pública (2026-11-11): `GET /search.json` con `q`,
`fields` y `limit`; 1 req/s sin identificar (3 con User-Agent+email). No se ha
llamado en vivo: NOT RUN.
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
    RespuestaNoTransitoria,
    pedir_con_cortesia,
)

logger = structlog.get_logger()

SITIO = "https://openlibrary.org"
CUBIERTAS = "https://covers.openlibrary.org"
USER_AGENT = "ZascArr/0.1 (+https://github.com/juanajok/zascarr)"
#: Campos de búsqueda acotados; no se pide `*` (respuesta cara).
_CAMPOS = "key,title,first_publish_year,author_name,cover_i,edition_count,publisher,language"


@dataclass(frozen=True)
class OpenLibraryResult:
    work_id: str                 # OL…W (sin /works/)
    title: str
    start_year: int | None = None
    author_name: list[str] | None = None
    cover_id: int | None = None
    cover_url: str | None = None
    description: str | None = None
    site_url: str | None = None
    editorial: str | None = None
    idioma: str | None = None
    raw: dict | None = None


def _work_id(valor: object) -> str | None:
    """`/works/OL123W` → `OL123W`; solo acepta la forma de obra de Open Library."""
    if not isinstance(valor, str):
        return None
    limpio = valor.strip().rstrip("/").split("/")[-1]
    return limpio if limpio.startswith("OL") and limpio.endswith("W") else None


def _resultado(doc: dict) -> OpenLibraryResult | None:
    if not isinstance(doc, dict):
        return None
    work_id = _work_id(doc.get("key"))
    titulo = str(doc.get("title") or "").strip()
    if not work_id or not titulo:
        return None
    cover = doc.get("cover_i")
    try:
        cover_id = int(cover) if cover not in (None, "") else None
    except (TypeError, ValueError):
        cover_id = None
    editorial = doc.get("publisher")
    if isinstance(editorial, list):
        editorial = editorial[0] if editorial else None
    idioma = doc.get("language")
    if isinstance(idioma, list):
        idioma = idioma[0] if idioma else None
    autores = doc.get("author_name")
    return OpenLibraryResult(
        work_id=work_id, title=titulo,
        start_year=doc.get("first_publish_year"),
        author_name=([str(a) for a in autores if a] if isinstance(autores, list) else None),
        cover_id=cover_id,
        cover_url=(f"{CUBIERTAS}/b/id/{cover_id}-M.jpg" if cover_id else None),
        site_url=f"{SITIO}/works/{work_id}",
        editorial=str(editorial).strip() if editorial else None,
        idioma=str(idioma).strip() if idioma else None,
        raw=doc,
    )


class OpenLibraryClient:
    def __init__(self, *, politica: PoliticaFuente | None = None,
                 cortesia: CortesiaProceso | None = None,
                 reloj=time.monotonic, dormir=asyncio.sleep,
                 espera_max_s: float = 30.0, base_url: str | None = None,
                 transporte: httpx.AsyncBaseTransport | None = None):
        s = get_settings()
        self._base = (base_url or s.open_library_base_url).rstrip("/")
        self._politica = politica or politica_de("open_library", s)
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._transporte = transporte
        self._client: httpx.AsyncClient | None = None
        self.ultimas_peticiones = 0

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self._base, timeout=30.0, follow_redirects=False,
            transport=self._transporte,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def get_work(self, work_id: str) -> OpenLibraryResult | None:
        """`GET /works/{OL…W}.json`: ficha de UNA obra ya identificada (SCR7).

        404/vacío ⇒ None (el llamador marca la caché negativa de 30 días); rate-limit o red
        se propagan como `ErrorDePeticion` para que el enricher NO marque TTL.
        """
        if self._client is None:
            raise RuntimeError("Cliente de Open Library sin abrir: úsalo con `async with`.")
        limpio = _work_id(work_id)
        if limpio is None:
            return None
        self.ultimas_peticiones += 1
        try:
            r = await pedir_con_cortesia(
                self._client, "GET", f"{self._base}/works/{limpio}.json",
                politica=self._politica, espera_max_s=self._espera_max_s,
                cortesia=self._cortesia, reloj=self._reloj, dormir=self._dormir,
            )
        except RespuestaNoTransitoria as exc:
            if exc.codigo == 404:
                return None
            raise
        try:
            data = r.json()
        except ValueError as exc:
            raise ErrorDePeticion("respuesta JSON inválida de Open Library") from exc
        if not isinstance(data, dict) or not data:
            return None
        descripcion = data.get("description")
        if isinstance(descripcion, dict):
            descripcion = descripcion.get("value")
        return OpenLibraryResult(
            work_id=limpio,
            title=str(data.get("title") or "").strip(),
            start_year=data.get("first_publish_year"),
            description=str(descripcion).strip() if descripcion else None,
            site_url=f"{SITIO}/works/{limpio}",
            raw=data,
        )

    async def search_works(self, query: str, limit: int = 10) -> list[OpenLibraryResult]:
        """`GET /search.json?q=…&fields=…&limit=…`; una página, sin dumps."""
        query = (query or "").strip()
        self.ultimas_peticiones = 0
        if not query or limit <= 0:
            return []
        if self._client is None:
            raise RuntimeError("Cliente de Open Library sin abrir: úsalo con `async with`.")
        self.ultimas_peticiones += 1
        r = await pedir_con_cortesia(
            self._client, "GET",
            f"{self._base}/search.json?q={quote(query, safe='')}&fields={_CAMPOS}"
            f"&limit={min(limit, 25)}",
            politica=self._politica, espera_max_s=self._espera_max_s,
            cortesia=self._cortesia, reloj=self._reloj, dormir=self._dormir,
        )
        try:
            data = r.json()
        except ValueError as exc:
            raise ErrorDePeticion("respuesta JSON inválida de Open Library") from exc
        if not isinstance(data, dict) or not isinstance(data.get("docs"), list):
            raise ErrorDePeticion("respuesta inválida de Open Library")
        resultados: list[OpenLibraryResult] = []
        for doc in data["docs"]:
            resultado = _resultado(doc)
            if resultado is not None:
                resultados.append(resultado)
            if len(resultados) >= limit:
                break
        return resultados
