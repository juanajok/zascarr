"""
Cliente Comic Vine API.

Rate limit: 1 req/s (ToS). Sin caché compartida: lo que se guarda se guarda en PostgreSQL.
Documentación: https://comicvine.gamespot.com/api/documentation
"""
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from zascarr.config import get_settings
from zascarr.utils.cortesia import PoliticaFuente, politica_de
from zascarr.utils.peticiones import RespuestaNoTransitoria, pedir_con_cortesia

logger = structlog.get_logger()

#: #311 — la imagen que Comic Vine pone en `image.*_url` cuando una serie o un número NO
#: tiene portada (se ve como «Blank!»). Mismo nombre de fichero en todos los tamaños
#: (`original`, `scale_medium`, `square_avatar`…); se compara el nombre y no el servidor
#: porque las imágenes también se sirvieron desde `comicvine1.cbsistatic.com`. Evidencia
#: sin consultar la fuente: varios proyectos públicos la detectan por este nombre y los
#: datos simulados de un cliente de la API la llevan en `image.*_url`.
PORTADA_DE_RELLENO = "6373148-blank.png"


def es_portada_de_relleno(url: str | None) -> bool:
    """¿Es la imagen de relleno de Comic Vine (= «sin portada»)? Una URL ausente no lo es."""
    if not url:
        return False
    return urlparse(url).path.rsplit("/", 1)[-1] == PORTADA_DE_RELLENO


def _portada(item: dict) -> str | None:
    """La portada de un resultado, o `None` si no hay o si es la imagen de relleno."""
    url = (item.get("image") or {}).get("medium_url")
    return None if es_portada_de_relleno(url) else url


@dataclass
class CVResult:
    cv_id: int
    name: str
    description: str | None = None
    image_url: str | None = None
    start_year: int | None = None
    count_of_issues: int | None = None
    site_url: str | None = None
    raw: dict | None = None


@dataclass
class CVVolume:
    """Volumen de Comic Vine para detalle de edición (#465, PR-3).

    Campos observados/documentados de `/volume/4050-{id}/`; `publisher` es el nombre ya
    resuelto por la API (si viene como objeto) o `None`. `count_of_issues` es un RECUENTO,
    no el número del ejemplar.
    """
    cv_id: int
    name: str
    publisher: str | None = None
    start_year: int | None = None
    count_of_issues: int | None = None
    first_issue: dict | None = None
    last_issue: dict | None = None
    raw: dict | None = None
    peticiones: int = 1


@dataclass
class CVCredit:
    """Un creador citado en person_credits, con uno o más roles.

    Comic Vine devuelve el rol como texto libre y a veces varios separados
    por coma ("writer, plotter"): se guardan todos tal cual, sin adivinar.
    El mapeo a CreatorRole es responsabilidad del enricher, no del cliente.
    """
    cv_id: int | None
    name: str
    roles: list[str] = field(default_factory=list)


@dataclass
class CVIssueResult:
    cv_id: int
    issue_number: str | None = None
    description: str | None = None
    image_url: str | None = None
    #: Fecha de PORTADA tal como la da Comic Vine (YYYY-MM-DD); no es `Issue.release_date`.
    cover_date: str | None = None
    #: Fecha de VENTA (la que significa `Issue.release_date`, decisión PO 2026-11-13).
    store_date: str | None = None
    credits: list[CVCredit] = field(default_factory=list)
    #: Nombres de personaje tal como los declara Comic Vine (no inventados).
    characters: list[str] = field(default_factory=list)
    #: Nombres de saga/arco; hoy se piden y se documentan, pero no se persiste
    #: `story_arc_issues` (no hay relación inequívoca serie↔arco en la app).
    story_arcs: list[str] = field(default_factory=list)
    raw: dict | None = None


#: Alias de lectura para quien llame al detalle de número.
CVIssue = CVIssueResult

#: `User-Agent` de ZascArr para Comic Vine, en UN SOLO sitio. GameSpot bloquea con HTTP 403
#: («Anonymous Bot or Scraper Blocked») las peticiones con el User-Agent genérico de las
#: librerías (python-httpx, python-requests) o sin él; con uno propio responde normal (200, o
#: 401 «Invalid API Key» si la clave no vale). Lo usan el cliente real y la prueba de conexión
#: de Ajustes: si se separan, el botón da un 403 engañoso con una clave buena.
USER_AGENT = "ZascArr/0.1"


class ComicVineClient:
    BASE_URL = "https://comicvine.gamespot.com/api"

    def __init__(self, *, espera_max_s: float = 30.0,
                 politica: PoliticaFuente | None = None):
        """Sin estado de cadencia propio: la cortesía es del proceso (#134).

        `espera_max_s` es el presupuesto de espera de cada método (fondo: 30 s; una acción de UI
        pasa el suyo). No hay `_last_req` ni `_rate_limit` por instancia: dos clientes de la misma
        fuente comparten la cola del proceso.
        """
        s = get_settings()
        self._api_key = s.comicvine_api_key
        self._politica = politica or politica_de("comicvine", s)
        self._espera_max_s = espera_max_s
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL, timeout=30.0, follow_redirects=False,
            headers={"User-Agent": USER_AGENT})
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def _get(self, endpoint: str, params: dict) -> dict:
        # No mutar el dict del caller: params["api_key"] = ... antes escribía
        # en el diccionario que pasó quien llamó, un efecto secundario
        # invisible detectado en el peer review.
        request_params = {**params, "api_key": self._api_key, "format": "json"}
        if self._client is None:
            raise RuntimeError("Cliente de Comic Vine sin abrir: úsalo con `async with`.")
        r = await pedir_con_cortesia(
            self._client, "GET", f"{self.BASE_URL}{endpoint}",
            politica=self._politica, espera_max_s=self._espera_max_s,
            datos=request_params,
        )
        data = r.json()
        if data.get("error") != "OK":
            logger.warning("comicvine.api_error", error=data.get("error"))
        return data

    async def search_series(self, query: str, limit: int = 10) -> list[CVResult]:
        # Comic Vine no expone país/idioma ni filtramos después: pedir 50 sería 5x payload
        # inútil en la Pi. Se pide `limit` y se recorta por si la API devuelve más.
        data = await self._get("/search/", {
            "query": query, "resources": "volume", "limit": limit,
            "field_list": "id,name,description,image,start_year,count_of_issues,site_detail_url",
        })
        resultados = [CVResult(
            cv_id=item["id"], name=item.get("name", ""),
            description=item.get("description"),
            image_url=_portada(item),
            start_year=_safe_int(item.get("start_year")),
            count_of_issues=item.get("count_of_issues"),
            site_url=item.get("site_detail_url"),
            raw=item,
        ) for item in data.get("results", [])]
        return resultados[:limit]

    async def get_volume(self, volume_id: int) -> CVVolume | None:
        """`GET /volume/4050-{id}/`; 1 petición y `None` en 404.

        Sin `comicvine_api_key` NO se hace ninguna petición: el método levanta
        `RuntimeError` antes de construirla (la clave solo la añade `_get`).
        """
        if not self._api_key:
            raise RuntimeError("Comic Vine sin clave: no se puede pedir el volumen.")
        try:
            data = await self._get(
                f"/volume/4050-{int(volume_id)}/",
                {"field_list": ("id,name,publisher,start_year,count_of_issues,"
                                "first_issue,last_issue")},
            )
        except RespuestaNoTransitoria as exc:
            if exc.codigo == 404:
                return None
            raise
        item = data.get("results")
        if not isinstance(item, dict) or not item:
            return None
        return _parse_cv_volume(item)

    async def get_issue(self, issue_id: int) -> CVIssueResult | None:
        """`GET /issue/4000-{id}/`; 1 petición y `None` en 404."""
        if not self._api_key:
            raise RuntimeError("Comic Vine sin clave: no se puede pedir el número.")
        try:
            data = await self._get(
                f"/issue/4000-{int(issue_id)}/",
                {"field_list": "id,issue_number,cover_date,store_date,volume"},
            )
        except RespuestaNoTransitoria as exc:
            if exc.codigo == 404:
                return None
            raise
        item = data.get("results")
        if not isinstance(item, dict) or not item:
            return None
        return _parse_issue(item)

    async def get_issue_detail(self, issue_id: int) -> dict[str, Any]:
        data = await self._get(
            f"/issue/4000-{issue_id}/",
            {
                "field_list": (
                    "id,name,issue_number,volume,description,cover_date,store_date,image,"
                    "person_credits,character_credits,story_arc_credits"
                ),
            },
        )
        return data.get("results", {})

    async def find_issue(self, volume_id: int, issue_number: str) -> CVIssueResult | None:
        """Busca un número concreto dentro de un volumen ya conocido.

        Es la pieza que faltaba para el enricher: dado un volume_id (el
        comic_vine_id de una Series ya resuelta) y un issue_number, resuelve
        el issue exacto sin tener que adivinar su ID de Comic Vine.
        """
        data = await self._get("/issues/", {
            "filter": f"volume:{volume_id},issue_number:{issue_number}",
            "field_list": ("id,issue_number,description,image,cover_date,store_date,person_credits,"
                           "character_credits,story_arc_credits"),
            "limit": 1,
        })
        results = data.get("results", [])
        if not results:
            return None
        return _parse_issue(results[0])


def _parse_issue(item: dict) -> CVIssueResult:
    credits = []
    for pc in item.get("person_credits", []) or []:
        roles = [r.strip().lower() for r in (pc.get("role") or "").split(",") if r.strip()]
        if pc.get("name"):
            credits.append(CVCredit(cv_id=pc.get("id"), name=pc["name"], roles=roles))
    return CVIssueResult(
        cv_id=item["id"],
        issue_number=item.get("issue_number"),
        description=item.get("description"),
        image_url=_portada(item),
        cover_date=item.get("cover_date"),
        store_date=item.get("store_date"),
        credits=credits,
        characters=_nombres(item.get("character_credits")),
        story_arcs=_nombres(item.get("story_arc_credits")),
        raw=item,
    )


def _nombre_editorial(valor: Any) -> str | None:
    """La API documenta `publisher` como objeto; se acepta también nombre plano."""
    if isinstance(valor, dict):
        nombre = valor.get("name")
    elif isinstance(valor, str):
        nombre = valor
    else:
        nombre = None
    return str(nombre).strip() if nombre else None


def _parse_cv_volume(item: dict) -> CVVolume:
    first = item.get("first_issue")
    last = item.get("last_issue")
    return CVVolume(
        cv_id=int(item.get("id") or 0),
        name=str(item.get("name") or ""),
        publisher=_nombre_editorial(item.get("publisher")),
        start_year=_safe_int(item.get("start_year")),
        count_of_issues=_safe_int(item.get("count_of_issues")),
        first_issue=first if isinstance(first, dict) else None,
        last_issue=last if isinstance(last, dict) else None,
        raw=item,
        peticiones=1,
    )


def _nombres(valor: Any) -> list[str]:
    """Nombres de una lista de objetos `{name: ...}` de Comic Vine, sin duplicados de caja."""
    salida: list[str] = []
    vistos: set[str] = set()
    for item in valor or []:
        if not isinstance(item, dict):
            continue
        nombre = str(item.get("name") or "").strip()
        if not nombre or nombre.casefold() in vistos:
            continue
        vistos.add(nombre.casefold())
        salida.append(nombre)
    return salida


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
