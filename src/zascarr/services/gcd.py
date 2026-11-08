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
el endpoint de BÚSQUEDA por nombre no trae sinopsis ni portada a nivel de
serie (solo editorial, idioma, formato físico, lista de números). La web
de GCD sí muestra portada y datos ricos de la edición (p. ej. española);
si la API expone una URL de imagen aprovechable por número es una
evaluación pendiente (BACKLOG E7), no una conclusión. Hoy no sirve para
el enricher (B4), cerrado con Comic Vine/AniList/Tebeosfera (ADR-0002).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

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

_BASE_URL = "https://www.comics.org/api"

# GCD indexa por país/idioma, no por una "tradición" ZascArr — mapeo
# best-effort para sugerir una pista en el formulario de alta; no se
# preselecciona y el coleccionista elige antes de confirmar (mismo criterio
# que las otras tres fuentes, ver DiscoveryResult.tradition_guess).
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

#: País/idioma que identifican una edición española en GCD. GCD usa códigos ISO de dos
#: letras y, según la ficha, el nombre del idioma; se aceptan las variantes en minúsculas.
_PAIS_ESPANOL = "es"
_IDIOMAS_ESPANOLES = {"es", "spanish", "español", "espanol"}


def es_edicion_espanola(resultado: GCDResult) -> bool | None:
    """Clasifica una edición de GCD para el flujo de tebeo español.

    - `True`: país `ES` o idioma español (`es`/`spanish`/`español`, sin distinguir caja).
    - `False`: tiene país/idioma informado y no es español.
    - `None`: no informa ni país ni idioma; no se puede descartar (se conserva y se marca).

    Es una función pura: no toca red, ni base de datos, ni el contrato de `search_series`.
    """
    pais = (resultado.country or "").strip().lower()
    idioma = (resultado.language or "").strip().lower()
    if not pais and not idioma:
        return None
    return pais == _PAIS_ESPANOL or idioma in _IDIOMAS_ESPANOLES


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
    def tradition_guess(self) -> str | None:
        """La tradición que se deduce de país/idioma, o `None` si GCD no reconoce ninguno.

        `None` no es un valor ficticio: representa que la fuente no sugiere tradición. No se
        usa `other`.
        """
        if (self.country or "").lower() in _BRITISH_COUNTRIES:
            return "british"
        return _LANGUAGE_TRADITION.get((self.language or "").lower())


@dataclass(frozen=True)
class GCDSerie:
    """Respuesta CRUDA de `GET /api/series/{id}/` para el detalle de edición (#465).

    El servicio `detalle_edicion` la normaliza a `DetalleEdicion`; aquí no se inventan campos
    que la API no traiga. `publisher` es la URL de la editorial: el nombre exige otra petición
    (`get_publisher`) y, sin ella, queda como campo ausente.
    """
    gcd_id: int
    name: str
    year_began: int | None = None
    year_ended: int | None = None
    publisher: str | None = None       # URL de la editorial, NO su nombre
    language: str | None = None
    country: str | None = None
    publishing_format: str | None = None
    binding: str | None = None
    issue_count: int | None = None
    active_issues: list | None = None
    issue_descriptors: list | None = None
    raw: dict | None = None
    peticiones: int = 1

    @classmethod
    def desde_raw(cls, raw: dict, gcd_id: int) -> GCDSerie:
        """Construye la serie desde el `raw` de la búsqueda (0 peticiones de serie)."""
        publisher = raw.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("url") or publisher.get("api_url")
        if not isinstance(publisher, str) or not publisher:
            publisher = None
        return cls(
            gcd_id=gcd_id, name=str(raw.get("name") or ""),
            year_began=raw.get("year_began"), year_ended=raw.get("year_ended"),
            publisher=publisher,
            language=raw.get("language"), country=raw.get("country"),
            publishing_format=raw.get("publishing_format"), binding=raw.get("binding"),
            issue_count=raw.get("issue_count"), active_issues=raw.get("active_issues"),
            issue_descriptors=raw.get("issue_descriptors"), raw=raw, peticiones=0,
        )

    @property
    def site_url(self) -> str:
        return f"https://www.comics.org/series/{self.gcd_id}/"


def _url_de_gcd(url: str) -> bool:
    """Solo se piden URLs del mismo origen de la API (la publisher_url viene de la API)."""
    if not isinstance(url, str) or not url:
        return False
    try:
        destino, base = urlsplit(url), urlsplit(_BASE_URL)
        return (destino.scheme == base.scheme and destino.hostname == base.hostname
                and destino.port in (None, base.port, 443)
                and destino.username is None and destino.password is None)
    except ValueError:
        return False


class GCDClient:
    def __init__(self, *, politica: PoliticaFuente | None = None,
                 cortesia: CortesiaProceso | None = None,
                 reloj=time.monotonic, dormir=asyncio.sleep, espera_max_s: float = 30.0):
        s = get_settings()
        self._politica = politica or politica_de("gcd", s)
        self._cortesia = cortesia
        self._reloj = reloj
        self._dormir = dormir
        self._espera_max_s = espera_max_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL, timeout=30.0, follow_redirects=False,
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

    async def get_series(self, gcd_id: int) -> GCDSerie | None:
        """`GET /api/series/{id}/` por `pedir_con_cortesia` (1 petición, sin atajos)."""
        if self._client is None:
            raise RuntimeError("Cliente de GCD sin abrir: úsalo con `async with`.")
        if not isinstance(gcd_id, int) or gcd_id <= 0:
            return None
        try:
            r = await pedir_con_cortesia(
                self._client, "GET", f"{_BASE_URL}/series/{gcd_id}/",
                politica=self._politica, espera_max_s=self._espera_max_s,
                cortesia=self._cortesia,
                reloj=self._reloj, dormir=self._dormir,
            )
            data = r.json()
        except (RespuestaNoTransitoria, ErrorDePeticion, httpx.HTTPError, ValueError):
            logger.warning("gcd.get_series_failed", gcd_id=gcd_id)
            return None
        if not isinstance(data, dict):
            return None
        publisher = data.get("publisher")
        if isinstance(publisher, dict):
            publisher = publisher.get("url") or publisher.get("api_url")
        if not isinstance(publisher, str) or not publisher:
            publisher = None
        return GCDSerie(
            gcd_id=gcd_id, name=str(data.get("name") or ""),
            year_began=data.get("year_began"), year_ended=data.get("year_ended"),
            publisher=publisher,
            language=data.get("language"), country=data.get("country"),
            publishing_format=data.get("publishing_format"), binding=data.get("binding"),
            issue_count=data.get("issue_count"),
            active_issues=(data.get("active_issues")
                           if isinstance(data.get("active_issues"), list) else None),
            issue_descriptors=(data.get("issue_descriptors")
                                if isinstance(data.get("issue_descriptors"), list) else None),
            raw=data, peticiones=1,
        )

    async def get_publisher(self, publisher_url: str) -> str | None:
        """Nombre de la editorial de GCD, o `None`; 1 petición y solo al origen de la API."""
        if self._client is None:
            raise RuntimeError("Cliente de GCD sin abrir: úsalo con `async with`.")
        if not publisher_url or not _url_de_gcd(publisher_url):
            return None
        try:
            r = await pedir_con_cortesia(
                self._client, "GET", publisher_url,
                politica=self._politica, espera_max_s=self._espera_max_s,
                cortesia=self._cortesia,
                reloj=self._reloj, dormir=self._dormir,
            )
            data = r.json()
        except (RespuestaNoTransitoria, ErrorDePeticion, httpx.HTTPError, ValueError):
            logger.warning("gcd.get_publisher_failed")
            return None
        if not isinstance(data, dict):
            return None
        nombre = data.get("name")
        return str(nombre).strip() if nombre else None

    async def search_series(self, query: str, limit: int = 10) -> list[GCDResult]:
        query = (query or "").strip()
        if not query:
            return []
        if self._client is None:
            raise RuntimeError("Cliente de GCD sin abrir: úsalo con `async with`.")
        try:
            # Sin cadencia por instancia: cada petición y salto pasa por la cortesía del proceso.
            r = await pedir_con_cortesia(
                self._client, "GET", f"{_BASE_URL}/series/name/{quote(query, safe='')}/",
                politica=self._politica, espera_max_s=self._espera_max_s,
                cortesia=self._cortesia,
                reloj=self._reloj, dormir=self._dormir,
            )
            data = r.json()
        except ErrorDePeticion:
            # Sin query en el registro (privacidad §6.6).
            logger.warning("gcd.request_failed")
            return []
        except ValueError as exc:
            # JSON inválido (p.ej. Cloudflare interponiendo una página de
            # verificación en vez de la API): "sin resultado", nunca una
            # excepción que tumbe la búsqueda — mismo criterio que
            # Tebeosfera (services/tebeosfera.py) ante fallos de parseo.
            logger.warning("gcd.invalid_json", error=type(exc).__name__)
            return []
        results = []
        # Filtrar ANTES de recortar: si los primeros son extranjeros, la edición
        # española que viene detrás no se pierde sin pedir otra página.
        for item in data.get("results", []):
            gcd_id = _id_from_api_url(item.get("api_url", ""))
            if gcd_id is None:
                continue
            resultado = GCDResult(
                gcd_id=gcd_id, name=item.get("name", ""),
                year_began=item.get("year_began"), year_ended=item.get("year_ended"),
                language=item.get("language"), country=item.get("country"),
                site_url=f"https://www.comics.org/series/{gcd_id}/",
                raw=item,
            )
            if es_edicion_espanola(resultado) is False:
                continue
            results.append(resultado)
            if len(results) >= limit:
                break
        return results


def _id_from_api_url(api_url: str) -> int | None:
    """".../api/series/64252/" -> 64252"""
    parts = [p for p in api_url.rstrip("/").split("/") if p]
    return int(parts[-1]) if parts and parts[-1].isdigit() else None
