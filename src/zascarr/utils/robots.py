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
import math
import re
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
#: Tope por defecto del `Crawl-delay` si la configuración no lo trae (rango 5–300 en config).
CRAWL_DELAY_MAX_POR_DEFECTO_S = 60.0
#: Fuentes cuyos orígenes se pueden olvidar al cambiar su interruptor (M-4).
FUENTES_CON_ROBOTS = ("fandom_dc", "fandom_marvel", "reading_orders",
                      "continuity_guide", "comic_book_herald")


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
        #: Generación por origen: `olvidar` la sube y una evaluación en vuelo no resucita.
        self._generacion: dict[str, int] = {}
        #: Orígenes cuyo recorte de Crawl-delay ya se avisó mientras la entrada sigue viva.
        self._avisos_crawl: set[str] = set()
        #: Orígenes con `Crawl-delay: inf` (protego lo descarta; se conserva para el tope).
        self._crawl_infinito: set[str] = set()

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
        self._generacion.clear()
        self._avisos_crawl.clear()
        self._crawl_infinito.clear()

    def olvidar(self, origen: str) -> None:
        """Olvida el estado en memoria de un origen (M-4); el candado se conserva.

        No lanza con una entrada inválida. No invalida la fila de `http_cache` del cuerpo de
        robots.txt (24 h/12 h): solo se re-parsea/reintenta el estado de este proceso.
        """
        try:
            clave = _origen(str(origen))
        except (ValueError, TypeError):
            return
        if not clave or clave == "://":
            return
        self._cache.pop(clave, None)
        self._generacion[clave] = self._generacion.get(clave, 0) + 1
        self._avisos_crawl.discard(clave)
        self._crawl_infinito.discard(clave)

    def _maximo_crawl_delay(self) -> float:
        """El tope configurado; se lee en cada evaluación (cambiarlo no recarga robots)."""
        from zascarr.config import get_settings

        try:
            valor = float(get_settings().crawl_delay_max_s)  # type: ignore[attr-defined]
        except (AttributeError, KeyError, TypeError, ValueError):
            return CRAWL_DELAY_MAX_POR_DEFECTO_S
        if not math.isfinite(valor) or valor <= 0:
            return CRAWL_DELAY_MAX_POR_DEFECTO_S
        return valor

    def _recortar_crawl_delay(self, origen: str, declarado) -> float | None:
        """Recorta el valor crudo del parser al máximo configurado (M-4 / AC-01…05).

        `None`, no numérico, `NaN` o `<= 0` ⇒ None (sin cambio); `inf` o finito por encima del
        máximo ⇒ máximo. `aplicar_crawl_delay` sigue subiendo el intervalo local como antes.
        """
        if declarado is None:
            return None
        try:
            valor = float(declarado)
        except (TypeError, ValueError):
            return None
        if math.isnan(valor) or valor <= 0:
            return None
        maximo = self._maximo_crawl_delay()
        if math.isinf(valor) or valor > maximo:
            if origen not in self._avisos_crawl:
                self._avisos_crawl.add(origen)
                logger.warning("robots.crawl_delay_recortado", origen=origen,
                               declarado_s=valor, recortado_s=maximo, maximo_s=maximo)
            return maximo
        return valor

    async def evaluar(self, url: str, *,
                      descargar_robots_fn) -> tuple[bool, float | None]:
        """`(permitido, crawl_delay_s)` para `url`, descargando `robots.txt` si hace falta.

        `descargar_robots_fn(robots_url)` devuelve un `httpx.Response`; debe pasar por la
        cortesía y la caché del proyecto. Solo se llama en un fallo de caché del origen.
        """
        origen = _origen(url)
        generacion = self._generacion.get(origen, 0)
        entrada = self._cache.get(origen)
        if entrada is None or self._reloj() >= entrada.expira_monotonic:
            async with self._candado(origen):
                entrada = self._cache.get(origen)
                if entrada is None or self._reloj() >= entrada.expira_monotonic:
                    entrada = await self._cargar(origen, descargar_robots_fn)
                    # Una evaluación en vuelo devuelve su resultado, pero si el origen se
                    # olvidó mientras tanto NO resucita la entrada (M-4).
                    if self._generacion.get(origen, 0) == generacion:
                        self._cache[origen] = entrada
                        self._avisos_crawl.discard(origen)
        if entrada.estado == "unreachable_disallow":
            return False, None
        if entrada.estado == "unavailable_allow" or entrada.parser is None:
            return True, None
        permitido = entrada.parser.can_fetch(url, self.user_agent)
        retraso_crudo = entrada.parser.crawl_delay(self.user_agent)
        if retraso_crudo is None and origen in self._crawl_infinito:
            retraso_crudo = float("inf")   # protego convierte `inf` en None: se conserva el hecho
        retraso = self._recortar_crawl_delay(origen, retraso_crudo)
        return permitido, retraso

    async def _cargar(self, origen: str, descargar_robots_fn) -> EntradaRobots:
        """Descarga y clasifica `robots.txt` de un origen según la matriz RFC 9309."""
        robots_url = f"{origen}/robots.txt"
        ahora = self._reloj()
        self._crawl_infinito.discard(origen)
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
            if re.search(r"(?im)^\s*crawl-delay\s*:\s*(?:inf|infinity)\s*$", texto):
                self._crawl_infinito.add(origen)
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


def origenes_de_fuente(fuente: str) -> tuple[str, ...]:
    """Orígenes de robots.txt de una fuente (M-4); `()` si la fuente no usa robots.

    Imports perezosos a propósito: evita el ciclo robots ↔ adaptadores de fuentes.
    """
    if fuente in ("fandom_dc", "fandom_marvel"):
        from zascarr.services.fandom import FUENTES

        host = FUENTES.get(fuente)
        return (f"https://{host}",) if host else ()
    if fuente == "reading_orders":
        from zascarr.services.reading_orders.comicbookreadingorders import ORIGEN

        return (ORIGEN,)
    if fuente == "continuity_guide":
        from zascarr.services.reading_orders.continuity_guide import ORIGEN

        return (ORIGEN,)
    if fuente == "comic_book_herald":
        from zascarr.config import get_settings
        from zascarr.services.comicbook_herald import FEED_POR_DEFECTO

        try:
            url = str(get_settings().comic_book_herald_feed_url or "")
        except (AttributeError, KeyError, TypeError):
            url = ""
        origen = _origen(url or FEED_POR_DEFECTO)
        return (origen,) if origen and origen != "://" else ()
    # Foro, portadas y fuentes de enriquecimiento: no pasan por robots.txt.
    return ()


def olvidar_origenes_de_fuente(fuente: str) -> tuple[str, ...]:
    """Olvida los orígenes de una fuente si el gestor del proceso existe (M-4).

    Si aún no se ha instanciado, NO lo crea (no hay estado que olvidar) y devuelve el mapeo;
    así el arranque y los tests no pagan una instanciación por guardar Ajustes.
    """
    origenes = origenes_de_fuente(fuente)
    if _GESTOR_DE_PROCESO is not None:
        for origen in origenes:
            _GESTOR_DE_PROCESO.olvidar(origen)
    return origenes


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
    "CRAWL_DELAY_MAX_POR_DEFECTO_S",
    "FUENTES_CON_ROBOTS",
    "MAX_ROBOTS",
    "POLITICA_CACHE_ROBOTS",
    "USER_AGENT",
    "AccesoProhibidoPorRobots",
    "EntradaRobots",
    "EstadoRobots",
    "GestorRobots",
    "aplicar_crawl_delay",
    "gestor_robots_de_proceso",
    "olvidar_origenes_de_fuente",
    "origenes_de_fuente",
]
