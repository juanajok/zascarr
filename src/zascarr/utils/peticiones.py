# ruff: noqa: E501
"""Envoltura común de peticiones externas con cortesía (#134, MIT-M8-US02).

Una sola definición de «cada petición, cada salto y cada reintento pasan por la cola»: la usan los
clientes de fuentes migrados (Comic Vine y AniList en el corte 1a; el resto después) y la prueba de
conexión de Ajustes.

Reglas que aplica (spec §3–§5):
- La fuente apagada se comprueba **antes** de reservar y antes de cada intento/salto (la prueba
  manual de Ajustes es la excepción explícita: `permitir_apagada=True`).
- Cada petición y cada salto se autorizan con el limitador de dos niveles (fuente + host efectivo) y
  cuentan en el presupuesto `espera_max_s` del llamador.
- Redirecciones a mano: `follow_redirects=False`, tope de la política (3), solo el mismo origen (o el
  permiso explícito `hosts_redireccion`); 301/302/303 → GET sin cuerpo, 307/308 conservan método y
  cuerpo; un bucle se corta por el tope. Un destino no permitido falla **antes** de pedirlo.
- Reintentos solo de transitorios (red/timeout, 408, 5xx, 429), con backoff 2, 4… (tope 30) y el
  máximo de la política. Un `Retry-After` se comparte como bloqueo de fuente y host; si no cabe en
  el presupuesto, espera visible sin dormir.
- Los errores llevan un **código corto**, nunca la URL ni la query (§6.6).
"""
from __future__ import annotations

import asyncio
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx
import structlog

from zascarr.utils.cortesia import (
    CortesiaEnEspera,
    FuenteApagada,
    PoliticaFuente,
    cortesia_de_proceso,
    fuente_habilitada,
    host_efectivo,
    origen_normalizado,
)

logger = structlog.get_logger()

CODIGOS_REDIRECCION = frozenset({301, 302, 303, 307, 308})
CODIGOS_SIN_CUERPO_TRAS_SALTO = frozenset({301, 302, 303})
_MAXIMO_BLOQUEO_S = 3600.0


class ErrorDePeticion(Exception):  # noqa: N818 — nombre del contrato (§3.6)
    """Base de los fallos de una petición externa: lleva un código corto, nunca la URL."""


class RedireccionNoPermitida(ErrorDePeticion):  # noqa: N818 — nombre del contrato (§3.6)
    """`Location` ausente, malformado, con credenciales, de otro origen o fuera de la allowlist."""

    def __init__(self, host: str, motivo: str):
        self.host = host
        self.motivo = motivo
        super().__init__(f"redirección no permitida ({motivo}) en {host or 'destino desconocido'}")


class DemasiadasRedirecciones(ErrorDePeticion):  # noqa: N818 — nombre del contrato (§3.6)
    """Se alcanzó el tope de saltos de la política: no se envía el siguiente."""

    def __init__(self, maximo: int):
        self.maximo = maximo
        super().__init__(f"demasiadas redirecciones (máximo {maximo})")


class ReintentosAgotados(ErrorDePeticion):  # noqa: N818 — nombre del contrato (§3.6)
    """Transitorios agotados: `intentos` intentos y `ultimo_codigo` (None si fue de red)."""

    def __init__(self, fuente: str, intentos: int, ultimo_codigo: int | None):
        self.fuente = fuente
        self.intentos = intentos
        self.ultimo_codigo = ultimo_codigo
        super().__init__(f"reintentos agotados en {fuente} ({intentos}, último {ultimo_codigo})")


class RespuestaNoTransitoria(ErrorDePeticion):  # noqa: N818 — nombre del contrato (§3.6)
    """Un 4xx que no es 408/429: no se reintenta."""

    def __init__(self, codigo: int):
        self.codigo = codigo
        super().__init__(f"respuesta no transitoria: HTTP {codigo}")


def _cabeceras_sin_cuerpo(cabeceras: dict | None) -> dict | None:
    if not cabeceras:
        return cabeceras
    return {k: v for k, v in cabeceras.items()
            if k.lower() not in ("content-type", "content-length")}


def retry_after_s(valor: str | None) -> float | None:
    """Segundos de un `Retry-After` (número o fecha HTTP de la stdlib); None si falta o no vale."""
    if not valor:
        return None
    texto = valor.strip()
    try:
        segundos = float(texto)
    except ValueError:
        try:
            fecha = parsedate_to_datetime(texto)
        except (TypeError, ValueError):
            return None
        if fecha is None:
            return None
        segundos = (fecha - fecha.now(fecha.tzinfo)).total_seconds()
    if segundos <= 0:
        return None
    return min(segundos, _MAXIMO_BLOQUEO_S)


def _destino_seguro(actual: str, location: str | None, *, hosts_redireccion,
                    origen_inicial: str) -> str:
    """Resuelve `Location` y comprueba origen/allowlist ANTES de pedir el salto."""
    if not location or not location.strip():
        raise RedireccionNoPermitida(host_efectivo(actual), "location_ausente")
    destino = urljoin(actual, location.strip())
    partes = urlsplit(destino)
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise RedireccionNoPermitida("", "location_invalida")
    if partes.username or partes.password or "@" in (partes.netloc or ""):
        raise RedireccionNoPermitida(partes.hostname, "location_con_credenciales")
    origen = origen_normalizado(destino)
    permitido = (
        hosts_redireccion(origen) if hosts_redireccion is not None
        else origen == origen_inicial
    )
    if not permitido:
        raise RedireccionNoPermitida(partes.hostname, "otro_origen")
    return destino


async def _enviar(cliente: httpx.AsyncClient, metodo: str, url: str, *,
                  datos, cabeceras) -> httpx.Response:
    """Un salto, sin seguir redirecciones automáticas. GET lleva `params`, el resto `json`."""
    metodo = metodo.upper()
    if metodo == "GET" and datos is not None:
        return await cliente.get(url, params=datos, headers=cabeceras)
    if metodo == "POST" and datos is not None:
        return await cliente.post(url, json=datos, headers=cabeceras)
    return await cliente.request(metodo, url, headers=cabeceras)


async def _seguir_redirecciones(cliente, metodo: str, url: str, *, politica: PoliticaFuente,
                                deadline: float | None, hosts_redireccion,
                                datos, cabeceras, cortesia, reloj, motivo: str):
    """Una llamada con sus saltos: cada hop pasa por la cola y cuenta en el presupuesto."""
    origen_inicial = origen_normalizado(url)
    metodo_actual, url_actual, datos_actuales = metodo, url, datos
    cabeceras_actuales = cabeceras
    espera_total = 0.0
    for salto in range(0, politica.max_redirecciones + 1):
        host = host_efectivo(url_actual)
        restante = None if deadline is None else deadline - reloj()
        if restante is not None and restante <= 0:
            raise CortesiaEnEspera(politica.fuente, host, 0.0, motivo)
        espera = await cortesia.esperar(politica.fuente, host, motivo=motivo,
                                        espera_max_s=restante)
        espera_total += espera.espera_s
        respuesta = await _enviar(cliente, metodo_actual, url_actual,
                                  datos=datos_actuales, cabeceras=cabeceras_actuales)
        if respuesta.status_code not in CODIGOS_REDIRECCION:
            return respuesta, espera_total
        if salto >= politica.max_redirecciones:
            raise DemasiadasRedirecciones(politica.max_redirecciones)
        destino = _destino_seguro(url_actual, respuesta.headers.get("location"),
                                  hosts_redireccion=hosts_redireccion,
                                  origen_inicial=origen_inicial)
        if respuesta.status_code in CODIGOS_SIN_CUERPO_TRAS_SALTO:
            metodo_actual, datos_actuales = "GET", None
            cabeceras_actuales = _cabeceras_sin_cuerpo(cabeceras_actuales)
        url_actual = destino
    raise DemasiadasRedirecciones(politica.max_redirecciones)


def _es_transitorio(codigo: int) -> bool:
    return codigo in (408, 429) or 500 <= codigo <= 599


async def pedir_con_cortesia(
    cliente: httpx.AsyncClient, metodo: str, url: str, *,
    politica: PoliticaFuente,
    espera_max_s: float,
    hosts_redireccion=None,
    datos=None,
    cabeceras: dict | None = None,
    permitir_apagada: bool = False,
    cortesia=None,
    reloj=time.monotonic,
    dormir=asyncio.sleep,
) -> httpx.Response:
    """Hace la petición aplicando §3-§5 y devuelve una respuesta NO 3xx.

    `cliente` debe haberse creado con `follow_redirects=False`. `espera_max_s` cubre todas las
    esperas, saltos y reintentos de esta llamada. `hosts_redireccion` es un predicado sobre el
    origen normalizado del destino (por defecto, solo el mismo origen de la URL inicial).
    """
    servicio = cortesia or cortesia_de_proceso()
    servicio.registrar_politica(politica)
    if not permitir_apagada and not fuente_habilitada(politica.fuente):
        raise FuenteApagada(politica.fuente)
    deadline = reloj() + max(0.0, float(espera_max_s))
    ultimo_codigo: int | None = None
    for intento in range(1, max(1, politica.max_intentos) + 1):
        if not permitir_apagada and not fuente_habilitada(politica.fuente):
            raise FuenteApagada(politica.fuente)
        restante = deadline - reloj()
        if restante <= 0:
            raise CortesiaEnEspera(politica.fuente, host_efectivo(url), 0.0, "cortesia")
        espera_s_intento = 0.0
        try:
            respuesta, espera_s_intento = await _seguir_redirecciones(
                cliente, metodo, url, politica=politica, deadline=deadline,
                hosts_redireccion=hosts_redireccion, datos=datos, cabeceras=cabeceras,
                cortesia=servicio, reloj=reloj, motivo="cortesia" if intento == 1 else "reintento")
        except CortesiaEnEspera:
            raise
        except httpx.TimeoutException:
            ultimo_codigo = None
            servicio.registrar_resultado(politica.fuente, "red", intento=intento,
                                         espera_s=espera_s_intento)
            espera_backoff = politica.backoff_s(intento)
            if intento >= politica.max_intentos:
                raise ReintentosAgotados(politica.fuente, intento, None) from None
            restante = deadline - reloj()
            if restante < espera_backoff:
                raise CortesiaEnEspera(politica.fuente, host_efectivo(url), espera_backoff,
                                       "reintento") from None
            await dormir(espera_backoff)
            continue
        except httpx.TransportError:
            ultimo_codigo = None
            servicio.registrar_resultado(politica.fuente, "red", intento=intento,
                                         espera_s=espera_s_intento)
            espera_backoff = politica.backoff_s(intento)
            if intento >= politica.max_intentos:
                raise ReintentosAgotados(politica.fuente, intento, None) from None
            restante = deadline - reloj()
            if restante < espera_backoff:
                raise CortesiaEnEspera(politica.fuente, host_efectivo(url), espera_backoff,
                                       "reintento") from None
            await dormir(espera_backoff)
            continue

        codigo = respuesta.status_code
        if codigo == 429:
            ultimo_codigo = 429
            servicio.registrar_resultado(politica.fuente, "429", intento=intento,
                                         espera_s=espera_s_intento)
            segundos = None
            if politica.obedece_retry_after:
                segundos = retry_after_s(respuesta.headers.get("retry-after"))
            if segundos is None:
                segundos = politica.backoff_s(intento)
            servicio.bloquear(politica.fuente, host_efectivo(url), segundos, motivo="429")
            restante = deadline - reloj()
            if intento >= politica.max_intentos:
                raise ReintentosAgotados(politica.fuente, intento, 429)
            if restante < segundos:
                raise CortesiaEnEspera(politica.fuente, host_efectivo(url), segundos,
                                       "bloqueo_fuente")
            continue
        if codigo == 408 or 500 <= codigo <= 599:
            ultimo_codigo = codigo
            servicio.registrar_resultado(politica.fuente, str(codigo), intento=intento,
                                         espera_s=espera_s_intento)
            espera_backoff = politica.backoff_s(intento)
            if intento >= politica.max_intentos:
                raise ReintentosAgotados(politica.fuente, intento, codigo)
            restante = deadline - reloj()
            if restante < espera_backoff:
                raise CortesiaEnEspera(politica.fuente, host_efectivo(url), espera_backoff,
                                       "reintento")
            await dormir(espera_backoff)
            continue
        if 200 <= codigo < 300:
            servicio.registrar_resultado(politica.fuente, "ok", intento=intento,
                                         espera_s=espera_s_intento)
            return respuesta
        servicio.registrar_resultado(politica.fuente, "4xx", intento=intento,
                                     espera_s=espera_s_intento)
        raise RespuestaNoTransitoria(codigo)
    raise ReintentosAgotados(politica.fuente, politica.max_intentos, ultimo_codigo)
