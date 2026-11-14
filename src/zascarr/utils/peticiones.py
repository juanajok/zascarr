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
- RES-3 (#812): el cuerpo se lee **en streaming** con un tope real de bytes decodificados
  (`max_cuerpo_transfer_bytes`, 4 MiB por defecto). Un cuerpo mayor corta la lectura y lanza
  `CuerpoDemasiadoGrande` sin reintentar; `Content-Length` solo acelera el corte (puede faltar
  o mentir). Así una respuesta hostil no se bufferiza entera antes de ser rechazada.
"""
from __future__ import annotations

import asyncio
import math
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urljoin, urlsplit

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
#: Cabeceras que NO cruzan un cambio de origen (§4, condición de Seguridad C2).
CABECERAS_SENSIBLES = frozenset({
    "authorization", "proxy-authorization", "cookie", "x-api-key",
})
#: RES-3: tamaño de trozo al leer el cuerpo en streaming (64 KiB).
TROZO_LECTURA = 64 * 1024
#: RES-3: tope por defecto si la configuración no lo trae (config.py lo acota a 1–16 MiB).
MAX_CUERPO_TRANSFER_POR_DEFECTO = 4 * 1024 * 1024


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


class CuerpoDemasiadoGrande(ErrorDePeticion):  # noqa: N818 — nombre del contrato (§3.6)
    """El cuerpo supera `max_cuerpo_transfer_bytes`: se corta y NO se reintenta.

    Hereda de `ErrorDePeticion` (no de `RespuestaNoTransitoria`): un 2xx con cuerpo enorme no
    es un «4xx no reintentable» ni debe crear una negativa en la caché. El mensaje no lleva
    URL, query ni cuerpo; solo fuente, motivo, bytes leídos y límite.
    """

    def __init__(self, fuente: str, *, bytes_leidos: int, limite: int, motivo: str):
        self.fuente = fuente
        self.bytes_leidos = int(bytes_leidos)
        self.limite = int(limite)
        self.motivo = motivo
        super().__init__(
            f"cuerpo demasiado grande en {fuente} "
            f"({self.bytes_leidos}/{self.limite} B, {motivo})")


def _limite_de_cuerpo() -> int:
    """El tope configurado (`max_cuerpo_transfer_bytes`); lectura perezosa de `get_settings`."""
    from zascarr.config import get_settings

    try:
        limite = int(get_settings().max_cuerpo_transfer_bytes)  # type: ignore[attr-defined]
    except (AttributeError, KeyError, TypeError, ValueError):
        # Dobles de prueba con `__getattr__` estricto u objetos viejos sin el campo.
        return MAX_CUERPO_TRANSFER_POR_DEFECTO
    return limite if limite > 0 else MAX_CUERPO_TRANSFER_POR_DEFECTO


def _longitud_declarada(valor: str | None) -> int | None:
    """`Content-Length` como entero no negativo, o None si falta/no es válido (solo una pista)."""
    if valor is None or not str(valor).strip().isdigit():
        return None
    try:
        return int(str(valor).strip())
    except (TypeError, ValueError):
        return None


def _aviso_de_corte(fuente: str, motivo: str, bytes_leidos: int, limite: int,
                    host: str) -> None:
    """Un único evento por petición cortada; nunca URL, query ni cuerpo (RES-3/§6.6)."""
    logger.warning("peticiones.cuerpo_demasiado_grande", fuente=fuente, motivo=motivo,
                   bytes_leidos=bytes_leidos, limite=limite, host=host)


def _cabeceras_sin_cuerpo(cabeceras: dict | None) -> dict | None:
    if not cabeceras:
        return cabeceras
    return {k: v for k, v in cabeceras.items()
            if k.lower() not in ("content-type", "content-length")}


def _cabeceras_sin_credenciales(cabeceras: dict | None) -> dict | None:
    """Un salto a OTRO origen no lleva `Authorization`/`X-Api-Key`/`Cookie`/`Proxy-Authorization`."""
    if not cabeceras:
        return cabeceras
    return {k: v for k, v in cabeceras.items() if k.lower() not in CABECERAS_SENSIBLES}


def retry_after_s(valor: str | None, maximo: float = 3600.0) -> float | None:
    """Segundos de un `Retry-After` (número o fecha HTTP de la stdlib); None si falta o no vale.

    Un `NaN`/`inf` no es un número de segundos: cae al backoff (nunca se convierte en bloqueo)."""
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
    if not math.isfinite(segundos) or segundos <= 0:
        return None
    return min(segundos, max(0.0, maximo))


def _destino_seguro(actual: str, location: str | None, *, hosts_redireccion,
                    origen_inicial: str) -> tuple[str, str]:
    """Resuelve `Location` y comprueba origen/allowlist ANTES de pedir el salto.

    Devuelve `(destino, origen)`. Un puerto no numérico o una IPv6 rota es `location_invalida`
    (fallo de redirección, sin reintento), no un error de red."""
    if not location or not location.strip():
        raise RedireccionNoPermitida(host_efectivo(actual), "location_ausente")
    try:
        destino = urljoin(actual, location.strip())
        partes = urlsplit(destino)
        origen = origen_normalizado(destino)
    except (ValueError, httpx.InvalidURL) as exc:
        raise RedireccionNoPermitida("", "location_invalida") from exc
    if partes.scheme not in ("http", "https") or not partes.hostname:
        raise RedireccionNoPermitida("", "location_invalida")
    if partes.username or partes.password or "@" in (partes.netloc or ""):
        raise RedireccionNoPermitida(partes.hostname, "location_con_credenciales")
    permitido = (
        hosts_redireccion(origen) if hosts_redireccion is not None
        else origen == origen_inicial
    )
    if not permitido:
        raise RedireccionNoPermitida(partes.hostname, "otro_origen")
    return destino, origen


def _cuerpo_de_formulario(datos, form_charset: str | None) -> tuple[bytes, dict | None]:
    """Cuerpo `x-www-form-urlencoded` en el charset pedido (SCR4) y su `Content-Type`.

    Sin `form_charset` se deja el comportamiento de siempre (httpx lo codifica en UTF-8).
    Un carácter que no cabe en el charset se reintenta en cp1252 (lo que ofrece IPB); si
    tampoco, se rechaza con un mensaje SIN los valores del formulario (podrían ser secretos).
    """
    if not form_charset:
        return None, None
    try:
        cuerpo = urlencode(datos, encoding=form_charset)
    except (UnicodeEncodeError, LookupError):
        try:
            cuerpo = urlencode(datos, encoding="cp1252")
        except UnicodeEncodeError:
            raise ValueError(
                "el formulario no se puede codificar en el charset del foro") from None
        form_charset = "cp1252"
    cabecera = {"Content-Type": f"application/x-www-form-urlencoded; charset={form_charset}"}
    return cuerpo.encode(form_charset, errors="strict"), cabecera


def _argumentos_de_peticion(metodo: str, datos, cabeceras: dict | None, form: bool,
                            form_charset: str | None):
    """`(kwargs, cabeceras)` de un salto: GET params; POST json o formulario (charset SCR4)."""
    metodo = metodo.upper()
    kwargs: dict = {}
    cabeceras_finales = dict(cabeceras or {})
    if metodo == "GET" and datos is not None:
        kwargs["params"] = datos
    elif metodo == "POST" and datos is not None:
        if form:
            cuerpo, extra = _cuerpo_de_formulario(datos, form_charset)
            if cuerpo is not None:
                kwargs["content"] = cuerpo
                cabeceras_finales.update(extra or {})
            else:
                kwargs["data"] = datos
        else:
            kwargs["json"] = datos
    return kwargs, (cabeceras_finales or None)


async def _leer_con_tope(cliente: httpx.AsyncClient, metodo: str, url: str, *,
                         datos, cabeceras, form: bool, form_charset: str | None,
                         fuente: str, host: str, deadline: float | None,
                         reloj=time.monotonic,
                         limite: int | None = None) -> httpx.Response:
    """Un salto con lectura **streaming** y tope real de bytes decodificados (RES-3).

    - 3xx: se devuelve sin leer el cuerpo (los saltos los resuelve `_seguir_redirecciones`).
    - `Content-Length` > límite: se corta antes de leer un solo trozo (`motivo="content_length"`).
    - Si no: `aiter_bytes(64 KiB)` acumula y corta en cuanto supera el límite
      (`motivo="chunks"`); cuenta bytes ya descomprimidos (cubre gzip-bomba).
    - Un goteo que agota `deadline` lanza `CortesiaEnEspera(..., "cuerpo_lento")`.
    - La `Response` devuelta conserva `.content/.text/.json()/.headers/.status_code/.request`.
    """
    limite = _limite_de_cuerpo() if limite is None else int(limite)
    kwargs, cabeceras_finales = _argumentos_de_peticion(
        metodo, datos, cabeceras, form, form_charset)
    async with cliente.stream(metodo.upper(), url, headers=cabeceras_finales,
                              **kwargs) as r:
        if r.status_code in CODIGOS_REDIRECCION:
            # No se lee el cuerpo de una redirección: el siguiente salto ya tiene su Location.
            return httpx.Response(r.status_code, headers=r.headers, content=b"",
                                  request=r.request)
        declarada = _longitud_declarada(r.headers.get("content-length"))
        if declarada is not None and declarada > limite:
            _aviso_de_corte(fuente, "content_length", 0, limite, host)
            raise CuerpoDemasiadoGrande(fuente, bytes_leidos=0, limite=limite,
                                        motivo="content_length")
        acumulado = bytearray()
        async for trozo in r.aiter_bytes(chunk_size=TROZO_LECTURA):
            acumulado.extend(trozo)
            if len(acumulado) > limite:
                _aviso_de_corte(fuente, "chunks", len(acumulado), limite, host)
                raise CuerpoDemasiadoGrande(fuente, bytes_leidos=len(acumulado),
                                            limite=limite, motivo="chunks")
            if deadline is not None and reloj() > deadline:
                raise CortesiaEnEspera(fuente, host, 0.0, "cuerpo_lento")
        # `aiter_bytes()` ya descomprimió el cuerpo. Si se conservan `Content-Encoding`
        # y `Content-Length`, el `Response` reconstruido intenta descomprimir otra vez
        # (`zlib.error: incorrect header check`) y la longitud ya no corresponde.
        cabeceras = [(k, v) for k, v in r.headers.multi_items()
                     if k.lower() not in ("content-encoding", "content-length")]
        return httpx.Response(r.status_code, headers=cabeceras,
                              content=bytes(acumulado), request=r.request)


async def _enviar(cliente: httpx.AsyncClient, metodo: str, url: str, *,
                  datos, cabeceras, form: bool,
                  form_charset: str | None = None,
                  fuente: str = "", host: str = "",
                  deadline: float | None = None, reloj=time.monotonic) -> httpx.Response:
    """Un salto, sin seguir redirecciones automáticas (lectura con tope, RES-3)."""
    return await _leer_con_tope(
        cliente, metodo, url, datos=datos, cabeceras=cabeceras, form=form,
        form_charset=form_charset, fuente=fuente, host=host, deadline=deadline,
        reloj=reloj)


async def _seguir_redirecciones(cliente, metodo: str, url: str, *, politica: PoliticaFuente,
                                deadline: float | None, hosts_redireccion,
                                datos, cabeceras, cortesia, reloj, motivo: str,
                                form: bool, permitir_apagada: bool,
                                form_charset: str | None = None):
    """Una llamada con sus saltos: cada hop pasa por la cola y cuenta en el presupuesto."""
    try:
        origen_inicial = origen_normalizado(url)
    except ValueError as exc:
        raise RedireccionNoPermitida("", "location_invalida") from exc
    metodo_actual, url_actual, datos_actuales = metodo, url, datos
    cabeceras_actuales = cabeceras
    espera_total = 0.0
    origen_actual = origen_inicial
    for salto in range(0, politica.max_redirecciones + 1):
        # La puerta de «fuente apagada» se comprueba antes de CADA salto, no solo antes del
        # primer intento: si se apaga mientras se sigue una redirección, no se envía.
        if not permitir_apagada and not fuente_habilitada(politica.fuente):
            raise FuenteApagada(politica.fuente)
        host = origen_actual                    # §3.2: (esquema, host, puerto)
        restante = None if deadline is None else deadline - reloj()
        if restante is not None and restante <= 0:
            raise CortesiaEnEspera(politica.fuente, host, 0.0, motivo)
        espera = await cortesia.esperar(politica.fuente, host, motivo=motivo,
                                        espera_max_s=restante)
        espera_total += espera.espera_s
        # La fuente pudo apagarse DURANTE la espera: se vuelve a mirar justo antes de enviar.
        if not permitir_apagada and not fuente_habilitada(politica.fuente):
            raise FuenteApagada(politica.fuente)
        try:
            respuesta = await _enviar(
                cliente, metodo_actual, url_actual,
                datos=datos_actuales, cabeceras=cabeceras_actuales,
                form=form, form_charset=form_charset,
                fuente=politica.fuente, host=host_efectivo(url_actual),
                deadline=deadline, reloj=reloj)
        except (httpx.RemoteProtocolError, httpx.InvalidURL) as exc:
            # La URL del salto no es protocolizable: fallo de redirección, no de red.
            raise RedireccionNoPermitida("", "location_invalida") from exc
        if respuesta.status_code not in CODIGOS_REDIRECCION:
            return respuesta, espera_total, origen_actual
        if salto >= politica.max_redirecciones:
            raise DemasiadasRedirecciones(politica.max_redirecciones)
        destino, origen_destino = _destino_seguro(
            url_actual, respuesta.headers.get("location"),
            hosts_redireccion=hosts_redireccion, origen_inicial=origen_inicial)
        if origen_destino != origen_inicial:
            # Condición de Seguridad C2: un salto a OTRO origen no reenvía credenciales
            # (cabeceras sensibles) ni datos (query/cuerpo con claves).
            cabeceras_actuales = _cabeceras_sin_credenciales(cabeceras_actuales)
            datos_actuales = None
        if respuesta.status_code in CODIGOS_SIN_CUERPO_TRAS_SALTO:
            metodo_actual, datos_actuales = "GET", None
            form_charset = None
            cabeceras_actuales = _cabeceras_sin_cuerpo(cabeceras_actuales)
        url_actual, origen_actual = destino, origen_destino
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
    form: bool = False,
    form_charset: str | None = None,
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
            raise CortesiaEnEspera(politica.fuente, origen_normalizado(url), 0.0, "cortesia")
        espera_s_intento = 0.0
        try:
            respuesta, espera_s_intento, origen_final = await _seguir_redirecciones(
                cliente, metodo, url, politica=politica, deadline=deadline,
                hosts_redireccion=hosts_redireccion, datos=datos, cabeceras=cabeceras,
                cortesia=servicio, reloj=reloj,
                motivo="cortesia" if intento == 1 else "reintento",
                form=form, permitir_apagada=permitir_apagada,
                form_charset=form_charset)
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
                raise CortesiaEnEspera(politica.fuente, origen_normalizado(url), espera_backoff,
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
                raise CortesiaEnEspera(politica.fuente, origen_normalizado(url), espera_backoff,
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
                segundos = retry_after_s(respuesta.headers.get("retry-after"),
                                        politica.bloqueo_max_s)
            if segundos is None:
                segundos = politica.backoff_s(intento)
            origen = origen_final
            servicio.bloquear(politica.fuente, origen, segundos, motivo="429",
                              maximo_s=politica.bloqueo_max_s)
            restante = deadline - reloj()
            # Primero el presupuesto: un bloqueo que no cabe es ESPERA visible (no fallo de red),
            # aunque ya no quedaran intentos (§3.7/§6.5).
            if restante < segundos:
                raise CortesiaEnEspera(politica.fuente, origen, segundos, "bloqueo_fuente")
            if intento >= politica.max_intentos:
                raise ReintentosAgotados(politica.fuente, intento, 429)
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
                raise CortesiaEnEspera(politica.fuente, origen_normalizado(url), espera_backoff,
                                       "reintento")
            await dormir(espera_backoff)
            continue
        if 200 <= codigo < 300:
            servicio.registrar_resultado(politica.fuente, "ok", intento=intento,
                                         espera_s=espera_s_intento)
            return respuesta
        # M-5 (SecOps): un 304 es «sin cambios», no un rechazo 4xx.
        servicio.registrar_resultado(politica.fuente,
                                     "304" if codigo == 304 else "4xx",
                                     intento=intento, espera_s=espera_s_intento)
        raise RespuestaNoTransitoria(codigo)
    raise ReintentosAgotados(politica.fuente, politica.max_intentos, ultimo_codigo)
