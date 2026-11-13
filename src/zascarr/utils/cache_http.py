"""Caché HTTP condicional en PostgreSQL con *singleflight* y topes de memoria (SCR1).

Por qué existe (Fase 1 del estudio de fuentes externas, ADR 0018): las APIs de guías y las
wikis no cambian cada minuto, pero el enricher y Descubrir repetían la misma consulta. Aquí
se guarda la respuesta **positiva** comprimida (zlib, ≤2 MiB) con sus validadores
(`ETag`/`Last-Modified`) y dos horizontes: `fresh_until` (se sirve sin red) y `retain_until`
(hasta ahí se revalida con un 304; después la purga la borra). Las **negativas** cortas
(`404`/`410`, o el `missingtitle` de MediaWiki) se recuerdan unas horas para no repetir una
página que no existe. `429`/`5xx`/fallo de red **no** se cachean: son transitorios.

Reglas que aplica:
- **La fuente apagada se mira primero** (`FuenteApagada` antes de leer la caché y de robots).
- Un **hit vigente no gasta turno de cortesía ni abre socket** (`x-zascarr-cache: hit`).
- **Singleflight** por `url_hash`: cinco corrutinas con la misma URL fría hacen **una**
  petición; el candado es de módulo, ligado al bucle y débil (no crece la RAM con las URLs).
- **robots.txt** se evalúa antes de ir a la red (nunca para un hit ni para robots.txt) y su
  `Crawl-delay` sube el intervalo mínimo de la política; el gestor de robots va aparte
  (`utils/robots.py`), que descarga su propio cuerpo por esta misma caché.
- El cuerpo se comprime y descomprime en `asyncio.to_thread` (CLAUDE.md §4); una fila
  corrupta o que supera el tope se descarta. La URL canónica redacta credenciales.

Depende de que haya un solo proceso (`uvicorn --workers 1`), como el resto de la cortesía.
"""
from __future__ import annotations

import asyncio
import hashlib
import time
import weakref
import zlib
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from zascarr.models import HttpCache
from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    FuenteApagada,
    PoliticaFuente,
    cortesia_de_proceso,
    fuente_habilitada,
    host_efectivo,
)
from zascarr.utils.peticiones import (
    RespuestaNoTransitoria,
    pedir_con_cortesia,
)

if TYPE_CHECKING:  # evita el ciclo cache_http -> robots -> cache_http en tiempo de import
    from zascarr.utils.robots import GestorRobots

logger = structlog.get_logger()

#: Tope del cuerpo que se persiste, descomprimido (2 MiB). Lo que lo supera no se guarda.
MAX_CUERPO_CACHE = 2 * 1024 * 1024
#: Nivel de compresión (equilibrio CPU/tamaño; el cuerpo es JSON o wikitext muy comprimible).
ZLIB_LEVEL = 6
#: Cabecera de diagnóstico: `hit` o `revalidada` (nunca se sirve de la red).
CABECERA_ESTADO = "x-zascarr-cache"
#: Parámetros de query cuyo VALOR no se guarda en `url_canonical` (pueden ser credenciales).
PARAMETROS_SENSIBLES = frozenset({
    "api_key", "apikey", "key", "token", "access_token", "refresh_token",
    "password", "sig", "signature",
})
REDACTADO = "REDACTADO"


# ── Candado de *singleflight* (por URL, por bucle y sin crecer) ─────────────────────────────────

#: Un `asyncio.Lock` queda atado al bucle que lo usa (las pruebas usan uno por test) y no
#: debe sobrevivir a él: un `WeakKeyDictionary` por bucle + valores débiles por `url_hash`.
_CANDADOS_POR_BUCLE: weakref.WeakKeyDictionary[
    object, weakref.WeakValueDictionary[str, asyncio.Lock]
] = weakref.WeakKeyDictionary()


def candado_de_singleflight(clave: str) -> asyncio.Lock:
    """El candado compartido de `clave` en el bucle actual, mientras haya corrutinas usándolo."""
    bucle = asyncio.get_running_loop()
    candados = _CANDADOS_POR_BUCLE.get(bucle)
    if candados is None:
        candados = weakref.WeakValueDictionary()
        _CANDADOS_POR_BUCLE[bucle] = candados
    candado = candados.get(clave)
    if candado is None:
        candado = asyncio.Lock()
        candados[clave] = candado
    return candado


def reiniciar_candados_para_pruebas() -> None:
    """Olvida los candados de todos los bucles (las pruebas reinician estado global)."""
    _CANDADOS_POR_BUCLE.clear()


# ── URL canónica, hash y compresión ─────────────────────────────────────────────────────────────

def _netloc_sin_credenciales(partes) -> str:
    """Host (con corchetes si es IPv6) y puerto solo si no es el de por defecto."""
    host = (partes.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    puerto = partes.port
    if puerto is None or (partes.scheme == "http" and puerto == 80) \
            or (partes.scheme == "https" and puerto == 443):
        return host
    return f"{host}:{puerto}"


def normalizar_y_hashear_url(metodo: str, url: str,
                             params: dict[str, Any] | None = None) -> tuple[str, str, str]:
    """`(url_hash, url_canonical, domain)` de una petición.

    Quita el userinfo de la URL, ordena la query (incluidos los `params` extra del GET),
    minúsculas en esquema/host y fuera los puertos por defecto. El **hash** se calcula sobre
    la URL completa (dos claves distintas no colapsan); `url_canonical`, que sí se guarda,
    redacta los valores de `PARAMETROS_SENSIBLES`.
    """
    partes = urlsplit(url)
    netloc = _netloc_sin_credenciales(partes)
    esquema = (partes.scheme or "").lower()
    pares = list(parse_qsl(partes.query, keep_blank_values=True))
    if params:
        pares.extend((str(clave), str(valor)) for clave, valor in params.items()
                     if valor is not None)
    pares.sort(key=lambda par: (par[0], par[1]))
    url_completa = urlunsplit(
        (esquema, netloc, partes.path or "/", urlencode(pares, doseq=True), ""))
    pares_redactados = [
        (clave, REDACTADO if clave.lower() in PARAMETROS_SENSIBLES else valor)
        for clave, valor in pares
    ]
    url_canonical = urlunsplit(
        (esquema, netloc, partes.path or "/", urlencode(pares_redactados, doseq=True), ""))
    material = f"{metodo.upper()} {url_completa}".encode()
    return hashlib.sha256(material).hexdigest(), url_canonical, (partes.hostname or "").lower()


def comprimir_cuerpo(cuerpo: bytes) -> bytes | None:
    """Comprime si no supera `MAX_CUERPO_CACHE`; `None` si es demasiado grande."""
    if len(cuerpo) > MAX_CUERPO_CACHE:
        return None
    return zlib.compress(cuerpo, level=ZLIB_LEVEL)


def descomprimir_cuerpo(comprimido: bytes) -> bytes | None:
    """Descomprime con tope; `None` si la fila está corrupta o supera `MAX_CUERPO_CACHE`."""
    descompresor = zlib.decompressobj()
    try:
        cuerpo = descompresor.decompress(comprimido, MAX_CUERPO_CACHE)
    except zlib.error:
        return None
    if descompresor.unconsumed_tail or not descompresor.eof:
        return None
    return cuerpo


# ── Política de caché y fila desacoplada del ORM ───────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class PoliticaCacheDominio:
    """TTL de un recurso: positivo, margen de revalidación y negativa (`frozen`, pura)."""

    ttl_positivo: timedelta
    margen_retencion_304: timedelta
    ttl_negativo: timedelta
    codigos_negativos: frozenset[int] = frozenset()

    def calcular_ventanas(self, ahora: datetime,
                          *, es_negativo: bool) -> tuple[datetime, datetime]:
        """`(fresh_until, retain_until)`; una negativa no se revalida (ambos iguales)."""
        if es_negativo:
            fin = ahora + self.ttl_negativo
            return fin, fin
        fresco = ahora + self.ttl_positivo
        return fresco, fresco + self.margen_retencion_304


@dataclass(slots=True)
class FilaCache:
    """Una fila de `http_cache` ya desacoplada del ORM (la usan también las cachés falsas)."""

    url_hash: str
    url_canonical: str
    domain: str
    status_code: int
    content_type: str | None
    is_negative: bool
    etag: str | None
    last_modified: str | None
    body_zlib: bytes | None
    fetched_at: datetime
    fresh_until: datetime
    retain_until: datetime


class CacheHttpProtocolo(Protocol):
    """Lo que `pedir_con_cache` necesita de una caché (Postgres en producción, falsa en tests)."""

    async def leer(self, url_hash: str) -> FilaCache | None: ...

    async def escribir(self, fila: FilaCache) -> None: ...

    async def renovar(self, url_hash: str, *, fetched_at: datetime,
                      fresh_until: datetime, retain_until: datetime) -> int: ...

    async def purgar(self, ahora: datetime | None = None) -> int: ...


class CacheHttp:
    """Repositorio Postgres de `http_cache`: una sesión corta propia por operación.

    Nunca usa la sesión del ciclo del enricher (esa está a mitad de transacción): cada
    lectura/escritura abre su sesión, hace `commit` y la cierra: es el patrón de `get_db`.
    """

    def __init__(self, sesion_factory: Callable[[], Any]):
        self._sesion_factory = sesion_factory

    @staticmethod
    def _a_fila(fila: HttpCache) -> FilaCache:
        return FilaCache(
            url_hash=fila.url_hash, url_canonical=fila.url_canonical, domain=fila.domain,
            status_code=fila.status_code, content_type=fila.content_type,
            is_negative=bool(fila.is_negative), etag=fila.etag,
            last_modified=fila.last_modified, body_zlib=fila.body_zlib,
            fetched_at=fila.fetched_at, fresh_until=fila.fresh_until,
            retain_until=fila.retain_until,
        )

    async def leer(self, url_hash: str) -> FilaCache | None:
        async with self._sesion_factory() as sesion:
            fila = (await sesion.execute(
                select(HttpCache).where(HttpCache.url_hash == url_hash)
            )).scalar_one_or_none()
        return self._a_fila(fila) if fila is not None else None

    async def escribir(self, fila: FilaCache) -> None:
        valores = {
            "url_hash": fila.url_hash, "url_canonical": fila.url_canonical,
            "domain": fila.domain, "status_code": fila.status_code,
            "content_type": fila.content_type, "is_negative": fila.is_negative,
            "etag": fila.etag, "last_modified": fila.last_modified,
            "body_zlib": fila.body_zlib, "fetched_at": fila.fetched_at,
            "fresh_until": fila.fresh_until, "retain_until": fila.retain_until,
        }
        sentencia = pg_insert(HttpCache).values(**valores)
        actualizables = {clave: valor for clave, valor in valores.items()
                         if clave != "url_hash"}
        sentencia = sentencia.on_conflict_do_update(
            index_elements=["url_hash"], set_=actualizables)
        async with self._sesion_factory() as sesion:
            await sesion.execute(sentencia)
            await sesion.commit()

    async def renovar(self, url_hash: str, *, fetched_at: datetime,
                      fresh_until: datetime, retain_until: datetime) -> int:
        async with self._sesion_factory() as sesion:
            resultado = await sesion.execute(
                update(HttpCache).where(HttpCache.url_hash == url_hash).values(
                    fetched_at=fetched_at, fresh_until=fresh_until,
                    retain_until=retain_until))
            await sesion.commit()
        return int(resultado.rowcount or 0)

    async def purgar(self, ahora: datetime | None = None) -> int:
        """Borra las filas cuyo `retain_until` ya pasó (nunca solo por `fresh_until`)."""
        momento = ahora if ahora is not None else datetime.now(UTC)
        async with self._sesion_factory() as sesion:
            resultado = await sesion.execute(
                delete(HttpCache).where(HttpCache.retain_until < momento))
            await sesion.commit()
        return int(resultado.rowcount or 0)


# ── Lectura de un hit ──────────────────────────────────────────────────────────────────────────

def _cabeceras_de_fila(fila: FilaCache, estado: str) -> dict[str, str]:
    cabeceras = {CABECERA_ESTADO: estado}
    if fila.content_type:
        cabeceras["content-type"] = fila.content_type
    return cabeceras


async def _respuesta_de_fila(fila: FilaCache, estado: str) -> httpx.Response | None:
    """Respuesta servida desde la caché, o None si la fila está corrupta (se trata como fallo)."""
    if fila.is_negative and fila.status_code >= 400:
        raise RespuestaNoTransitoria(fila.status_code)
    if fila.body_zlib is None:
        cuerpo = b""
    else:
        cuerpo = await asyncio.to_thread(descomprimir_cuerpo, fila.body_zlib)
        if cuerpo is None:
            logger.warning("cache_http.fila_corrupta", url_hash=fila.url_hash[:12])
            return None
    return httpx.Response(fila.status_code, content=cuerpo,
                          headers=_cabeceras_de_fila(fila, estado))


def _es_robots(url: str) -> bool:
    try:
        return urlsplit(url).path == "/robots.txt"
    except ValueError:
        return False


# ── punto de entrada ──────────────────────────────────────────────────────────────────────────

async def pedir_con_cache(
    cliente: httpx.AsyncClient, metodo: str, url: str, *,
    politica: PoliticaFuente,
    politica_cache: PoliticaCacheDominio,
    cache: CacheHttpProtocolo,
    robots: GestorRobots | None = None,
    espera_max_s: float,
    clasificar: Callable[[httpx.Response], str] | None = None,
    bypass_cache: bool = False,
    datos: Any = None,
    cabeceras: dict | None = None,
    hosts_redireccion=None,
    permitir_apagada: bool = False,
    cortesia=None,
    reloj=time.monotonic,
    dormir=asyncio.sleep,
    ahora: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> httpx.Response:
    """GET con caché condicional, *singleflight* y robots (ver docstring del módulo).

    `cache` es cualquier `CacheHttpProtocolo` (Postgres en producción, falsa en tests) y
    `robots` un `GestorRobots`; si robots es None no se evalúa. Solo admite GET.
    `clasificar(respuesta)` devuelve `"ok"`, `"negativo"` o `"no_cachear"`; un fallo del
    clasificador nunca tumba la petición (se trata como `no_cachear`).
    """
    if metodo.upper() != "GET":
        raise ValueError("pedir_con_cache solo admite GET")
    servicio = cortesia or cortesia_de_proceso()
    # 1) Fuente apagada primero: ni caché ni robots ni socket.
    if not permitir_apagada and not fuente_habilitada(politica.fuente):
        raise FuenteApagada(politica.fuente)
    url_hash, url_canonical, domain = normalizar_y_hashear_url(metodo, url, datos)
    fila: FilaCache | None = None

    async def mirar_cache() -> httpx.Response | None:
        """Hit vigente, o None. Deja en `fila` la última leída (aunque sea stale)."""
        nonlocal fila
        if bypass_cache:
            return None
        fila = await cache.leer(url_hash)
        if fila is None or ahora() >= fila.fresh_until:
            return None
        return await _respuesta_de_fila(fila, "hit")

    respuesta = await mirar_cache()
    if respuesta is not None:
        logger.info("cache_http.hit", url_hash=url_hash[:12], domain=domain)
        return respuesta

    candado: asyncio.Lock | None = None
    if not bypass_cache:
        # 3) Singleflight: una sola petición por URL fría; el resto espera y relee.
        candado = candado_de_singleflight(url_hash)
        try:
            await asyncio.wait_for(candado.acquire(), timeout=max(0.0,espera_max_s))
        except TimeoutError as exc:
            raise CortesiaEnEspera(politica.fuente, host_efectivo(url),
                                   espera_max_s, "candado") from exc
    try:
        if candado is not None:
            respuesta = await mirar_cache()
            if respuesta is not None:
                logger.info("cache_http.hit", url_hash=url_hash[:12], domain=domain)
                return respuesta

        politica_red = await _politica_con_robots(
            robots, url, politica, cache=cache, cliente=cliente,
            hosts_redireccion=hosts_redireccion, permitir_apagada=permitir_apagada,
            servicio=servicio, reloj=reloj, dormir=dormir, ahora=ahora,
            espera_max_s=espera_max_s)

        cabeceras_red = dict(cabeceras or {})
        if fila is not None and not fila.is_negative:
            if fila.etag:
                cabeceras_red["If-None-Match"] = fila.etag
            elif fila.last_modified:
                cabeceras_red["If-Modified-Since"] = fila.last_modified

        try:
            respuesta = await pedir_con_cortesia(
                cliente, metodo, url, politica=politica_red,
                espera_max_s=espera_max_s, hosts_redireccion=hosts_redireccion,
                datos=datos, cabeceras=cabeceras_red or None,
                permitir_apagada=permitir_apagada, cortesia=servicio,
                reloj=reloj, dormir=dormir,
            )
        except RespuestaNoTransitoria as exc:
            # 5) 304: revalidada con el cuerpo guardado (mismos validadores, sin cuerpo nuevo).
            if exc.codigo == 304 and fila is not None and not fila.is_negative:
                return await _devolver_revalidada(cache, fila, url_hash,
                                                  politica_cache=politica_cache,
                                                  ahora=ahora)
            # 6) Negativa corta por código HTTP: se recuerda y se relanza tal cual.
            if exc.codigo in politica_cache.codigos_negativos:
                await _guardar_negativa(cache, url_hash, url_canonical, domain,
                                        exc.codigo, politica_cache=politica_cache,
                                        ahora=ahora)
            raise

        # 6) Éxito 2xx: decide el clasificador (un fallo suyo no tumba la petición).
        clasificacion = "ok"
        if clasificar is not None:
            try:
                clasificacion = clasificar(respuesta)
            except Exception:
                logger.warning("cache_http.clasificador_fallido", url_hash=url_hash[:12])
                clasificacion = "no_cachear"
        if clasificacion not in ("ok", "negativo", "no_cachear"):
            clasificacion = "no_cachear"
        if clasificacion == "no_cachear":
            return respuesta

        cuerpo = respuesta.content or b""
        comprimido = await asyncio.to_thread(comprimir_cuerpo, cuerpo)
        if comprimido is None:
            logger.info("cache_http.cuerpo_demasiado_grande", url_hash=url_hash[:12],
                        bytes=len(cuerpo), limite=MAX_CUERPO_CACHE)
            return respuesta
        es_negativa = clasificacion == "negativo"
        momento = ahora()
        fresco, retenido = politica_cache.calcular_ventanas(momento, es_negativo=es_negativa)
        await cache.escribir(FilaCache(
            url_hash=url_hash, url_canonical=url_canonical, domain=domain,
            status_code=respuesta.status_code,
            content_type=respuesta.headers.get("content-type"),
            is_negative=es_negativa,
            etag=None if es_negativa else respuesta.headers.get("etag"),
            last_modified=None if es_negativa else respuesta.headers.get("last-modified"),
            body_zlib=comprimido, fetched_at=momento,
            fresh_until=fresco, retain_until=retenido,
        ))
        logger.info("cache_http.guardada", url_hash=url_hash[:12], domain=domain,
                    negativa=es_negativa)
        return respuesta
    finally:
        if candado is not None:
            candado.release()


async def _politica_con_robots(robots: GestorRobots | None, url: str,
                               politica: PoliticaFuente, **contexto) -> PoliticaFuente:
    """Evalúa robots.txt (si toca) y devuelve la política con su `Crawl-delay` aplicado."""
    if robots is None or _es_robots(url):
        return politica
    from zascarr.utils.robots import (
        POLITICA_CACHE_ROBOTS,
        AccesoProhibidoPorRobots,
        aplicar_crawl_delay,
    )

    espera_max_s = contexto["espera_max_s"]

    async def descargar_robots(robots_url: str) -> httpx.Response:
        """Descarga /robots.txt por la MISMA caché; 4xx se convierte en respuesta."""
        try:
            return await pedir_con_cache(
                contexto["cliente"], "GET", robots_url,
                politica=politica, politica_cache=POLITICA_CACHE_ROBOTS,
                cache=contexto["cache"], robots=None,
                espera_max_s=min(float(espera_max_s), 10.0),
                hosts_redireccion=contexto["hosts_redireccion"],
                permitir_apagada=contexto["permitir_apagada"],
                cortesia=contexto["servicio"], reloj=contexto["reloj"],
                dormir=contexto["dormir"], ahora=contexto["ahora"],
            )
        except RespuestaNoTransitoria as exc:
            return httpx.Response(exc.codigo)

    permitido, retraso = await robots.evaluar(url, descargar_robots_fn=descargar_robots)
    if not permitido:
        raise AccesoProhibidoPorRobots(politica.fuente, host_efectivo(url))
    if retraso is not None:
        politica = aplicar_crawl_delay(politica, retraso)
        contexto["servicio"].registrar_politica(politica)
    return politica


async def _devolver_revalidada(cache: CacheHttpProtocolo, fila: FilaCache, url_hash: str,
                               *, politica_cache: PoliticaCacheDominio,
                               ahora: Callable[[], datetime]) -> httpx.Response:
    """Renueva la fila con un 304 y sirve el cuerpo guardado (sin bajarlo otra vez)."""
    momento = ahora()
    fresco, retenido = politica_cache.calcular_ventanas(momento, es_negativo=False)
    fila = replace(fila, fetched_at=momento, fresh_until=fresco, retain_until=retenido)
    renovadas = await cache.renovar(url_hash, fetched_at=momento, fresh_until=fresco,
                                   retain_until=retenido)
    if renovadas == 0:  # la purga la borró mientras tanto: se reescribe con el cuerpo guardado
        await cache.escribir(fila)
    logger.info("cache_http.revalidada", url_hash=url_hash[:12])
    respuesta = await _respuesta_de_fila(fila, "revalidada")
    if respuesta is None:  # no debería: el cuerpo venía de una fila válida
        raise RespuestaNoTransitoria(304)
    return respuesta


async def _guardar_negativa(cache: CacheHttpProtocolo, url_hash: str, url_canonical: str,
                            domain: str, codigo: int, *,
                            politica_cache: PoliticaCacheDominio,
                            ahora: Callable[[], datetime]) -> None:
    """Guarda una negativa por código HTTP (sin cuerpo): se relanza al llamador."""
    momento = ahora()
    fresco, retenido = politica_cache.calcular_ventanas(momento, es_negativo=True)
    await cache.escribir(FilaCache(
        url_hash=url_hash, url_canonical=url_canonical, domain=domain,
        status_code=codigo, content_type=None, is_negative=True, etag=None,
        last_modified=None, body_zlib=None, fetched_at=momento,
        fresh_until=fresco, retain_until=retenido,
    ))
    logger.info("cache_http.negativa_guardada", url_hash=url_hash[:12], codigo=codigo)


# ── Purga periódica (una vez por ciclo del enricher) ───────────────────────────────────────────

async def purgar_cache(sesion_factory: Callable[[], Any] | None = None) -> int:
    """Purga las filas caducadas con la sesión por defecto del proceso (para `main.py`)."""
    if sesion_factory is None:
        from zascarr.database import async_session_factory
        sesion_factory = async_session_factory
    try:
        return await CacheHttp(sesion_factory).purgar()
    except Exception:
        logger.exception("cache_http.purga_fallida")
        return 0


__all__ = [
    "MAX_CUERPO_CACHE",
    "ZLIB_LEVEL",
    "CacheHttp",
    "CacheHttpProtocolo",
    "FilaCache",
    "PoliticaCacheDominio",
    "candado_de_singleflight",
    "comprimir_cuerpo",
    "descomprimir_cuerpo",
    "normalizar_y_hashear_url",
    "pedir_con_cache",
    "purgar_cache",
]
