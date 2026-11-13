"""Evaluación de `robots.txt` conforme a RFC 9309 con `protego` (SCR1, Fase 1).

Qué hace y por qué así:
- Se pide `robots.txt` **una vez por origen** y se guarda su estado en memoria, con
  *singleflight* por origen (dos consultas simultáneas al mismo sitio piden un solo fichero).
- Matriz RFC 9309 §2.3.1:
  * **2xx** → se parsea (`protego`, portada `content[:512*1024]` porque RFC 9309 exige
    interpretar al menos 500 KiB) y se aplican `Disallow` y `Crawl-delay` (24 h).
  * **4xx ≠ 429** → «no disponible» ⇒ permitido, con la política local (12 h). Es lo que
    devuelve Fandom (WAF con 403) y muchas guías (404).
  * **429, 5xx, fallo de red o parse que lanza** → «no se pudo comprobar» ⇒ se prohíbe
    temporalmente (15 min). Un 5xx NUNCA se recuerda como permiso.
- `FuenteApagada`, `CortesiaEnEspera`, `RedireccionNoPermitida` y `DemasiadasRedirecciones`
  se propagan: son política o presupuesto del llamador, no indisponibilidad del sitio.
- El cuerpo 200 lo persiste la caché HTTP (`utils/cache_http.py`): `evaluar` recibe una
  función de descarga y no toca la red por su cuenta. El estado (estado + parser + TTL) vive
  solo en memoria del proceso.
- `aplicar_crawl_delay` solo **sube** el `intervalo_min_s` de la política de cortesía: el
  `Crawl-delay` de la wiki nunca acelera lo que la configuración ya exige.

UA: `ZascArr/<versión>` (identificable, sin datos de la persona). Depende de un solo proceso
(`uvicorn --workers 1`), como `cortesia.py` y `cache_http.py`.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, replace
from datetime import timedelta
from importlib.metadata import PackageNotFoundError, version
from typing import Literal
from urllib.parse import urlsplit

import httpx
import structlog
from protego import Protego

from zascarr.utils.cache_http import PoliticaCacheDominio
from zascarr.utils.cortesia import PoliticaFuente
from zascarr.utils.peticiones import ErrorDePeticion, ReintentosAgotados

logger = structlog.get_logger()

#: UA identificable del proyecto (paquete `zascarr`). Respaldo si los metadatos no están.
try:
    USER_AGENT = f"ZascArr/{version('zascarr')}"
except PackageNotFoundError:  # pragma: no cover - solo si se ejecuta sin instalar
    USER_AGENT = "ZascArr"

#: Tope de lo que se lee de `robots.txt`: RFC 9309 exige interpretar al menos 500 KiB.
MAX_ROBOTS = 512 * 1024


def _origen(url: str) -> str:
    """`scheme://host[:puerto]` de una URL (clave de la caché en memoria)."""
    partes = urlsplit(url)
    return f"{partes.scheme.lower()}://{partes.netloc.lower()}"


EstadoRobots = Literal["parsed", "unavailable_allow", "unreachable_disallow"]


@dataclass(frozen=True, slots=True)
class EntradaRobots:
    """Estado cacheado de un origen: qué se concluyó y hasta cuándo vale (`reloj` monotónico)."""

    estado: EstadoRobots
    parser: Protego | None
    expira_monotonic: float


class AccesoProhibidoPorRobots(ErrorDePeticion):  # noqa: N818 — nombre del contrato
    """`robots.txt` prohíbe consultar esta fuente: no se envía la petición.

    Lleva la fuente y el host, nunca la URL ni la query (mismo contrato que `peticiones.py`).
    """

    def __init__(self, fuente: str, origen: str):
        self.fuente = fuente
        self.origen = origen
        super().__init__(f"robots.txt prohíbe consultar {fuente} en {origen}")


#: Política de caché del propio `robots.txt`: 24 h el cuerpo, 12 h la negativa (4xx ≠ 429).
POLITICA_CACHE_ROBOTS = PoliticaCacheDominio(
    ttl_positivo=timedelta(hours=24),
    margen_retencion_304=timedelta(days=14),
    ttl_negativo=timedelta(hours=12),
    codigos_negativos=frozenset(set(range(400, 500)) - {429}),
)


def aplicar_crawl_delay(politica: PoliticaFuente,
                        crawl_delay: float | None) -> PoliticaFuente:
    """Sube `intervalo_min_s` al `Crawl-delay` declarado (solo sube; nunca acelera)."""
    if crawl_delay is None:
        return politica
    try:
        retraso = float(crawl_delay)
    except (TypeError, ValueError):
        return politica
    if not retraso > 0:
        return politica
    return replace(politica,
                   intervalo_min_s=max(float(politica.intervalo_min_s), retraso))


class GestorRobots:
    """Caché en memoria de `robots.txt` por origen, con *singleflight* y reloj inyectable."""

    TTL_OK_S = 86_400.0          # 24 h: 2xx parseado
    TTL_UNAVAILABLE_S = 43_200.0  # 12 h: 4xx ≠ 429 (RFC 9309 §2.3.1.3)
    TTL_UNREACHABLE_S = 900.0     # 15 min: 429/5xx/red (RFC 9309 §2.3.1.4)

    def __init__(self, user_agent: str = USER_AGENT, reloj=time.monotonic):
        self.user_agent = user_agent
        self._reloj = reloj
        self._cache: dict[str, EntradaRobots] = {}
        self._candados: dict[str, tuple[object, asyncio.Lock]] = {}

    def _candado(self, origen: str) -> asyncio.Lock:
        """Candado del origen, atado al bucle actual (las pruebas usan uno por test)."""
        bucle = asyncio.get_running_loop()
        actual = self._candados.get(origen)
        if actual is None or actual[0] is not bucle:
            actual = (bucle, asyncio.Lock())
            self._candados[origen] = actual
        return actual[1]

    def reiniciar(self) -> None:
        """Olvida todo el estado (pruebas y apagado/encendido de fuentes)."""
        self._cache.clear()
        self._candados.clear()

    async def evaluar(self, url: str, *,
                      descargar_robots_fn) -> tuple[bool, float | None]:
        """`(permitido, crawl_delay_s)` para `url`, descargando `robots.txt` si hace falta.

        `descargar_robots_fn(robots_url)` devuelve un `httpx.Response`; debe pasar por la
        cortesía y la caché del proyecto. Solo se llama en un fallo de caché del origen.
        """
        origen = _origen(url)
        entrada = self._cache.get(origen)
        if entrada is None or self._reloj() >= entrada.expira_monotonic:
            async with self._candado(origen):
                entrada = self._cache.get(origen)
                if entrada is None or self._reloj() >= entrada.expira_monotonic:
                    entrada = await self._cargar(origen, descargar_robots_fn)
                    self._cache[origen] = entrada
        if entrada.estado == "unreachable_disallow":
            return False, None
        if entrada.estado == "unavailable_allow" or entrada.parser is None:
            return True, None
        permitido = entrada.parser.can_fetch(url, self.user_agent)
        retraso = entrada.parser.crawl_delay(self.user_agent)
        return permitido, (float(retraso) if retraso is not None else None)

    async def _cargar(self, origen: str, descargar_robots_fn) -> EntradaRobots:
        """Descarga y clasifica `robots.txt` de un origen según la matriz RFC 9309."""
        robots_url = f"{origen}/robots.txt"
        ahora = self._reloj()
        try:
            respuesta = await descargar_robots_fn(robots_url)
        except (ReintentosAgotados, httpx.TransportError):
            # No se pudo comprobar (red o transitorios agotados): prohibido 15 min, sin cachear
            # como permiso (RFC 9309 §2.3.1.4).
            return EntradaRobots("unreachable_disallow", None,
                                 ahora + self.TTL_UNREACHABLE_S)

        codigo = respuesta.status_code
        if 200 <= codigo < 300:
            texto = respuesta.content[:MAX_ROBOTS].decode("utf-8", "replace")
            try:
                parser = Protego.parse(texto)
            except Exception:
                logger.warning("robots.parse_fallido", origen=origen)
                return EntradaRobots("unreachable_disallow", None,
                                     ahora + self.TTL_UNREACHABLE_S)
            return EntradaRobots("parsed", parser, ahora + self.TTL_OK_S)
        if codigo == 429 or codigo >= 500:
            return EntradaRobots("unreachable_disallow", None,
                                 ahora + self.TTL_UNREACHABLE_S)
        if 400 <= codigo < 500:
            return EntradaRobots("unavailable_allow", None,
                                 ahora + self.TTL_UNAVAILABLE_S)
        return EntradaRobots("unreachable_disallow", None, ahora + self.TTL_UNREACHABLE_S)


_GESTOR_DE_PROCESO: GestorRobots | None = None


def gestor_robots_de_proceso() -> GestorRobots:
    """El gestor compartido del proceso (uno; creado al primer uso)."""
    global _GESTOR_DE_PROCESO
    if _GESTOR_DE_PROCESO is None:
        _GESTOR_DE_PROCESO = GestorRobots()
    return _GESTOR_DE_PROCESO


def _reiniciar_gestor_compartido() -> None:
    global _GESTOR_DE_PROCESO
    if _GESTOR_DE_PROCESO is not None:
        _GESTOR_DE_PROCESO.reiniciar()
    _GESTOR_DE_PROCESO = None


__all__ = [
    "MAX_ROBOTS",
    "POLITICA_CACHE_ROBOTS",
    "USER_AGENT",
    "AccesoProhibidoPorRobots",
    "EntradaRobots",
    "EstadoRobots",
    "GestorRobots",
    "aplicar_crawl_delay",
    "gestor_robots_de_proceso",
]
