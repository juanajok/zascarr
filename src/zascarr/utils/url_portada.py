# ruff: noqa: E501
"""Política de descarga de portadas externas (H1): qué URLs se pueden pedir desde el servidor y cómo.

Una portada se guarda como URL (`Series.cover_url`) y la descarga **el servidor**. Esa URL puede venir de un
formulario, de la API o de lo que devuelva una fuente, así que hay que tratarla como **no fiable** (SSRF):
sin esto, quien pueda crear o editar una serie puede hacer que el servidor pida un destino elegido por él
(incluidos servicios de la propia máquina) y deducir cosas por el tiempo de respuesta.

Defensa en capas (cada una la prueba una mutación):

1. **Sintaxis** (`analizar_url`): solo `http`/`https`, sin usuario ni contraseña, sin dirección IP escrita a mano,
   puerto implícito o el por defecto de su esquema, nombre ASCII y **de la lista de fuentes** (solo en la URL
   inicial: es la parte que controla quien escribe).
2. **Dirección resuelta** (`resolver_publica`): se resuelve el nombre y **todas** las direcciones (IPv4 e IPv6)
   deben ser públicas (lista explícita, la misma en toda versión de Python); una lista de nombres por sí sola no basta (*DNS rebinding*, o un nombre permitido que
   apunte a una dirección interna).
3. **Conexión a la dirección ya validada** (`_pedir`): se conecta a **esa IP** con el nombre en `Host` y en la
   SNI de TLS (el certificado se sigue verificando contra el **nombre**), de modo que no hay una segunda
   resolución entre la comprobación y la conexión.
4. **Redirecciones a mano**, como máximo 3 saltos y **cada salto pasa otra vez por 1-3** (los CDN de portadas
   redirigen con normalidad; prohibirlas rompería portadas legítimas). En los saltos no se exige la lista de
   fuentes —el CDN al que redirige puede ser otro—, pero sí todo lo demás.
5. **Tamaño máximo** y **tiempo total máximo**.

Un token firmado (Deseados, rebanada 2) garantiza la **integridad** de lo que vio la persona; **no** convierte
una URL externa en segura: por eso esta política vive en el punto que hace la petición.
"""
from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit

import httpx

#: Dominios (y sus subdominios) de los que se aceptan portadas. Son los mismos de `/ui/descubrir/portada`.
HOSTS_PERMITIDOS: tuple[str, ...] = (
    "comicvine.gamespot.com", "cbsistatic.com", "anilist.co", "tebeosfera.com", "comics.org",
)
LONGITUD_MAXIMA_URL = 500
MAX_SALTOS = 3
MAX_BYTES = 8 * 1024 * 1024
TIEMPO_TOTAL_S = 15.0
_CODIGOS_REDIRECCION = frozenset({301, 302, 303, 307, 308})
_PUERTO_POR_DEFECTO = {"http": 80, "https": 443}

#: IPv4 que NUNCA es un destino válido: el registro de direcciones de uso especial de la IANA. Lista EXPLÍCITA, sin
#: apoyarse en `is_global`/`is_reserved` (su resultado cambia entre versiones de Python y la CI usa otra que la
#: de desarrollo): la política es la misma en todas.
_V4_PROHIBIDAS = tuple(ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12",
    "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16", "198.18.0.0/15",
    "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
))
#: IPv6: solo el unicast global (`2000::/3`)…
_V6_UNICAST_GLOBAL = ipaddress.ip_network("2000::/3")
#: …menos sus rangos especiales: protocolos IETF (incluye Teredo y ORCHID), documentación y 6to4.
_V6_PROHIBIDAS = tuple(ipaddress.ip_network(n) for n in (
    "2001::/23", "2001:db8::/32", "2002::/16", "3fff::/20",
))

Resolutor = Callable[[str, int], Awaitable[list[str]]]
CreadorDeCliente = Callable[[], httpx.AsyncClient]


class UrlNoPermitidaError(ValueError):
    """La URL (o un salto de sus redirecciones) incumple la política. El mensaje es un CÓDIGO corto, sin la URL."""


def _fallo(codigo: str) -> UrlNoPermitidaError:
    return UrlNoPermitidaError(codigo)


# ── 1. Sintaxis ───────────────────────────────────────────────────────────────────────────────

def host_en_lista(host: str) -> bool:
    return any(host == d or host.endswith(f".{d}") for d in HOSTS_PERMITIDOS)


def analizar_url(url: str, *, exigir_lista: bool = True) -> tuple[str, str, int | None, str]:
    """(esquema, host, puerto explícito o None, ruta con consulta). Lanza `UrlNoPermitidaError` con un código corto."""
    if not isinstance(url, str) or not url or len(url) > (LONGITUD_MAXIMA_URL if exigir_lista else 2048):
        raise _fallo("longitud")
    if any(c <= " " or c == "\x7f" for c in url):
        raise _fallo("caracteres_de_control")
    try:
        partes = urlsplit(url)
        puerto = partes.port
    except ValueError:
        raise _fallo("url_mal_formada") from None
    esquema = partes.scheme.lower()
    if esquema not in _PUERTO_POR_DEFECTO:
        raise _fallo("esquema")
    if "@" in partes.netloc or partes.username is not None or partes.password is not None:
        raise _fallo("credenciales_en_la_url")
    host = (partes.hostname or "").rstrip(".")
    if not host or not host.isascii():
        raise _fallo("host")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise _fallo("direccion_ip_escrita")
    if puerto is not None and puerto != _PUERTO_POR_DEFECTO[esquema]:
        raise _fallo("puerto")
    if exigir_lista and not host_en_lista(host):
        raise _fallo("host_fuera_de_la_lista")
    ruta = partes.path or "/"
    if partes.query:
        ruta = f"{ruta}?{partes.query}"
    return esquema, host, puerto, ruta


def es_url_de_portada_permitida(url: str) -> bool:
    """¿Se puede GUARDAR esta URL como portada? (solo sintaxis y lista: no resuelve nada ni usa la red)."""
    try:
        analizar_url(url, exigir_lista=True)
    except UrlNoPermitidaError:
        return False
    return True


def host_para_log(url: str) -> str:
    """Solo el nombre de host, para los registros: nunca la URL entera (puede llevar credenciales o claves)."""
    try:
        return (urlsplit(url).hostname or "?")[:100]
    except ValueError:
        return "?"


# ── 2. Dirección resuelta ─────────────────────────────────────────────────────────────────────

def es_publica(texto: str) -> bool:
    """¿Es una dirección pública? Lista explícita (idéntica en todas las versiones de Python).

    IPv4: cualquiera fuera de los rangos de uso especial. IPv6: **solo** el unicast global, sin sus rangos
    especiales; por tanto NO pasa ninguna dirección de bucle local, local de enlace, local única, multicast, ni
    las que **incrustan** una IPv4 (mapeada `::ffff:a.b.c.d`, NAT64, 6to4, Teredo): `::ffff:127.0.0.1` es
    127.0.0.1, y ningún CDN legítimo llega por esos caminos."""
    try:
        ip = ipaddress.ip_address(texto.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv4Address):
        return not any(ip in red for red in _V4_PROHIBIDAS)
    return ip in _V6_UNICAST_GLOBAL and not any(ip in red for red in _V6_PROHIBIDAS)


async def resolver_dns(host: str, puerto: int) -> list[str]:
    """Resolución del sistema (no bloquea el bucle): todas las direcciones, sin repetir."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, puerto, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(i[4][0] for i in infos))


async def resolver_publica(host: str, puerto: int, resolutor: Resolutor) -> str:
    """La dirección a la que SE CONECTARÁ. **Todas** las que devuelva el nombre deben ser públicas (un nombre con
    una pública y una interna se rechaza: no se elige la «buena»)."""
    try:
        direcciones = await resolutor(host, puerto)
    except OSError:
        raise _fallo("no_resuelve") from None
    if not direcciones:
        raise _fallo("no_resuelve")
    if not all(es_publica(d) for d in direcciones):
        raise _fallo("direccion_no_publica")
    return direcciones[0]


# ── 3-5. Conexión fijada, redirecciones y tamaño ──────────────────────────────────────────────

def _cliente_por_defecto() -> httpx.AsyncClient:
    # `trust_env=False`: un proxy del entorno resolvería el nombre por su cuenta y anularía la dirección fijada.
    return httpx.AsyncClient(timeout=TIEMPO_TOTAL_S, follow_redirects=False, trust_env=False)


def _literal(ip: str) -> str:
    return f"[{ip}]" if ":" in ip else ip


async def _pedir(cliente: httpx.AsyncClient, esquema: str, host: str, ip: str, puerto: int | None,
                 ruta: str, max_bytes: int) -> tuple[int, str | None, bytes]:
    """Una petición a la dirección YA VALIDADA, con el nombre en `Host` y en la SNI de TLS.
    Devuelve (estado, destino, cuerpo): `destino` es `None` si NO es una redirección y, si lo es, el valor de
    `Location` (vacío si falta). Corta si el cuerpo supera `max_bytes`."""
    autoridad = _literal(ip) + (f":{puerto}" if puerto else "")
    cabeceras = {"Host": host if not puerto else f"{host}:{puerto}", "Accept": "image/*"}
    extensiones = {"sni_hostname": host} if esquema == "https" else {}
    async with cliente.stream("GET", f"{esquema}://{autoridad}{ruta}", headers=cabeceras,
                              extensions=extensiones) as r:
        if r.status_code in _CODIGOS_REDIRECCION:
            return r.status_code, r.headers.get("location") or "", b""
        r.raise_for_status()
        largo = r.headers.get("content-length", "")
        if largo.isdigit() and int(largo) > max_bytes:
            raise _fallo("demasiado_grande")
        cuerpo = bytearray()
        async for trozo in r.aiter_bytes():
            cuerpo += trozo
            if len(cuerpo) > max_bytes:
                raise _fallo("demasiado_grande")
        return r.status_code, None, bytes(cuerpo)


async def descargar_imagen(url: str, *, resolutor: Resolutor | None = None,
                           crear_cliente: CreadorDeCliente | None = None,
                           max_bytes: int = MAX_BYTES) -> bytes:
    """Los bytes de la portada, o `UrlNoPermitidaError` / un error de `httpx` si no se puede. La política se aplica
    en CADA salto; la URL inicial además debe ser de la lista de fuentes."""
    resolutor = resolutor or resolver_dns
    crear_cliente = crear_cliente or _cliente_por_defecto
    actual = url
    async with asyncio.timeout(TIEMPO_TOTAL_S):
        for salto in range(MAX_SALTOS + 1):
            esquema, host, puerto, ruta = analizar_url(actual, exigir_lista=(salto == 0))
            ip = await resolver_publica(host, puerto or _PUERTO_POR_DEFECTO[esquema], resolutor)
            async with crear_cliente() as cliente:
                _, destino, cuerpo = await _pedir(cliente, esquema, host, ip, puerto, ruta, max_bytes)
            if destino is None:
                return cuerpo
            if not destino:
                raise _fallo("redireccion_sin_destino")
            actual = urljoin(actual, destino)
    raise _fallo("demasiadas_redirecciones")
