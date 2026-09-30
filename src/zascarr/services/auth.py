"""
Autenticación (A6) — contraseña opcional para cuando ZascArr se expone
fuera de 127.0.0.1.

Deshabilitada por defecto (`auth_mode="none"`): SECURITY.md ya documenta
que el aislamiento por defecto es no publicar el puerto. Cuando se activa
("password" o "user_password" desde /ui/ajustes), esta pieza cubre dos
caminos de acceso distintos:

  - Navegador (UI Jinja2/HTMX): formulario /login → cookie de sesión
    firmada con HMAC-SHA256 (stdlib `hmac`, sin JWT ni dependencias
    nuevas — CLAUDE.md §2). La cookie solo demuestra "alguien presentó
    la contraseña correcta hace menos de SESSION_MAX_AGE segundos"; no
    hay usuarios ni roles, un solo operador.
  - Clientes de API (`curl`, scripts): HTTP Basic Auth por cabecera,
    sin cookie — permite seguir usando `/api/*` de forma programática.

Contraseñas nunca en claro: PBKDF2-HMAC-SHA256 (stdlib `hashlib`), mismo
espíritu que SECRET_FIELDS en runtime_settings.py — auth_password_hash
nunca se devuelve a la UI, solo se sobreescribe.
"""
from __future__ import annotations

import asyncio
import base64
import functools
import hashlib
import hmac
import html
import ipaddress
import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from zascarr.config import Settings, get_settings

COOKIE_NAME = "zascarr_session"
# 30 días: es una herramienta de un solo operador en su propia Pi, no un
# panel bancario — pedir la contraseña en cada visita sería fricción sin
# beneficio real de seguridad aquí.
SESSION_MAX_AGE = 30 * 24 * 3600
# Se queda en 260.000 hasta que el retraso progresivo y la caché de Basic estén
# en su sitio (ficha de seguridad, paso 3): subir a 600.000 sin eso dejaría que
# unas pocas peticiones paralelas agoten el ejecutor de PBKDF2. El hash guarda
# sus iteraciones, así que el cambio posterior será retrocompatible.
_PBKDF2_ITERATIONS = 260_000

# Ejecutor PROPIO para PBKDF2, no el `to_thread` por defecto: el ejecutor
# general lo comparten portadas, importador y etiquetado, y un PBKDF2 no debe
# poder acapararlo ni competir con ese trabajo. Dos hilos bastan en una Pi
# (es CPU-bound y no hay nada que ganar con más); el semáforo acota cuántas
# verificaciones quedan en vuelo para que una ráfaga no encole sin límite.
#
# Perezoso y recreable: el `lifespan` lo apaga al parar la app, y tras un
# apagado (o en un test que levanta otra vez la app) la siguiente verificación
# vuelve a crearlo en vez de fallar con «cannot schedule new futures after
# shutdown».
_PBKDF2_EXECUTOR: ThreadPoolExecutor | None = None
_pbkdf2_sem = asyncio.Semaphore(2)


def _ejecutor_pbkdf2() -> ThreadPoolExecutor:
    global _PBKDF2_EXECUTOR
    if _PBKDF2_EXECUTOR is None:
        _PBKDF2_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pbkdf2")
    return _PBKDF2_EXECUTOR


def apagar_ejecutor_pbkdf2() -> None:
    """Apaga el ejecutor propio de PBKDF2 al parar la app.

    `wait=False` para no bloquear el shutdown por un PBKDF2 en curso;
    `cancel_futures=True` para no dejar tareas encoladas. Se llama desde el
    `lifespan` de `main.py`; el ejecutor se recrea solo si vuelve a hacer
    falta."""
    global _PBKDF2_EXECUTOR
    if _PBKDF2_EXECUTOR is not None:
        _PBKDF2_EXECUTOR.shutdown(wait=False, cancel_futures=True)
        _PBKDF2_EXECUTOR = None

# Rutas alcanzables sin sesión ni Basic Auth incluso con auth_mode activo:
# /login (si no, nadie podría autenticarse nunca — bucle de redirección),
# /api/health (los healthchecks de Docker/monitorización no llevan
# credenciales), estáticos y el propio aviso legal (texto informativo,
# no hay nada que proteger ahí).
_RUTAS_EXENTAS = {"/login", "/api/health", "/legal", "/favicon.ico"}
_PREFIJOS_EXENTOS = ("/static/",)

# E6: en arranque degradado (BD inaccesible o sin migrar) solo se sirve
# diagnóstico — estas rutas y los estáticos. Todo lo demás falla cerrado.
_RUTAS_DIAGNOSTICO = {"/api/health", "/estado", "/login", "/legal"}


# ── CSRF / Origen / Host (ficha benchmark-seguridad-auth-origen-host) ─────────

_METODOS_DE_ESTADO = {"POST", "PUT", "PATCH", "DELETE"}


def _norm(url: str) -> tuple[str, str, str] | None:
    """(esquema, host, puerto) normalizado de una URL, o None si no es http/https,
    no tiene hostname, o trae un puerto inválido (`http://x:99999`,
    `http://x:abc`). Nunca revienta: un `Origin` malformado se rechaza, no da
    500."""
    try:
        partes = urlsplit(url)
        if partes.scheme not in ("http", "https"):
            return None
        hostname = partes.hostname
        puerto = partes.port or (443 if partes.scheme == "https" else 80)
    except ValueError:
        return None
    if not hostname:
        return None
    return (partes.scheme, hostname.lower(), str(puerto))


def _origen_permitido(origen: str, request: Request, settings: Settings) -> bool:
    """¿La cabecera Origin/Referer `origen` es este mismo sitio (Host de la
    petición o `base_url`), comparando esquema+host+puerto normalizados?

    `base_url` cubre el proxy inverso: nginx cambia `Host` por defecto, así que
    `Origin` es el dominio público y `Host` el interno — sin este caso toda la
    UI daría 403."""
    norm = _norm(origen)
    if norm is None:
        return False
    permitidos: set[tuple[str, str, str]] = set()
    propio = _norm(str(request.url))
    if propio:
        permitidos.add(propio)
    if settings.base_url:
        base = _norm(settings.base_url)
        if base:
            permitidos.add(base)
    return norm in permitidos


def _host_de_peticion(request: Request) -> str | None:
    """Hostname del `Host` (sin puerto ni corchetes de IPv6), o None si es
    malformado. `urlsplit("//" + host)` maneja bien `[::1]:8000` y `pi:8000`."""
    host = request.headers.get("host", "")
    try:
        return urlsplit(f"//{host}").hostname
    except ValueError:
        return None


def _es_ip_literal(hostname: str) -> bool:
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _hosts_permitidos_extra(settings: Settings) -> set[str]:
    """Nombres de `ALLOWED_HOSTS` (lista separada por comas) en minúsculas."""
    return {
        h.strip().lower()
        for h in (settings.allowed_hosts or "").split(",")
        if h.strip()
    }


def _host_no_permitido(request: Request, settings: Settings) -> bool:
    """True si el `Host` no es `localhost`, ni una IP literal (IPv4 o IPv6), ni
    el host de `base_url`, ni uno de `ALLOWED_HOSTS`.

    Solo se comprueba con `auth_mode = none`: un ataque de DNS rebinding hace
    que el navegador trate al atacante como mismo origen y pueda **leer**
    respuestas (biblioteca, wishlist, ajustes), así que la comprobación vale
    para TODOS los métodos, no solo los que cambian estado. Un rebinding
    necesita un NOMBRE DE DOMINIO que resuelva a la IP local; por eso las IP
    literales se dejan pasar — el navegador pide el dominio, no la IP — y los
    nombres que el dueño conoce se declaran en `ALLOWED_HOSTS`."""
    hostname = _host_de_peticion(request)
    if hostname is None:
        return True
    hostname = hostname.lower()
    if hostname == "localhost" or _es_ip_literal(hostname):
        return False
    if settings.base_url:
        base = _norm(settings.base_url)
        if base and base[1] == hostname:
            return False
    return hostname not in _hosts_permitidos_extra(settings)


def _peticion_cross_site(request: Request, settings: Settings) -> bool:
    """True si una petición que cambia estado es cross-site y debe rechazarse.

    `Sec-Fetch-Site` como señal principal (OWASP) y `Origin`/`Referer` de
    respaldo — obligatorio, porque los navegadores no mandan `Sec-Fetch-*` sobre
    HTTP plano hacia una IP de LAN. `Origin: null` (sandbox/redirección) se
    rechaza, y un `Referer` tipo `example.org.attacker.com` no pasa: la
    comparación es de origen normalizado completo, no de sufijo."""
    fetch_site = (request.headers.get("sec-fetch-site") or "").lower()
    if fetch_site == "cross-site":
        return True
    if fetch_site == "same-origin":
        # Señal positiva que calcula el navegador y una página no puede
        # falsificar: cubre el proxy con TLS que conserva `Host` pero la app ve
        # por http (Origin `https://…` vs URL `http://…`). En DNS rebinding
        # también llega `same-origin`, así que la comprobación de `Host` sigue
        # aplicándose aparte con `auth_mode=none`.
        return False

    origen = request.headers.get("origin")
    if origen is not None:
        return origen == "null" or not _origen_permitido(origen, request, settings)

    referer = request.headers.get("referer")
    if referer is not None:
        return not _origen_permitido(referer, request, settings)

    # Sin Origin ni Referer: en /ui/* se bloquea (un navegador manda Origin en un
    # POST); en /api/* se permite (scripts con curl/Basic).
    return request.url.path.startswith("/ui/")


def _respuesta_403(detalle: str, request: Request) -> Response:
    """403 con `Content-Type` explícito y `nosniff`.

    El texto lleva datos que envía el cliente (`Origin`, `Referer`, `Host`), así
    que se fija el tipo — sin `media_type`, Starlette no pone `Content-Type` y el
    navegador puede intentar adivinarlo — y se prohíbe el sniffing. Los valores
    van escapados con `html.escape` porque HTMX intercambia el cuerpo como
    `innerHTML` aunque sea `text/plain`."""
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=403, content={"detail": detalle})
    return Response(
        detalle, status_code=403,
        media_type="text/plain; charset=utf-8",
        headers={"X-Content-Type-Options": "nosniff"},
    )


def _respuesta_origen_rechazado(request: Request) -> Response:
    """403 en español, con el origen recibido y la salida concreta — nunca un
    código crudo. La vía de recuperación es `BASE_URL` en el `.env` (o Ajustes),
    para que quien esté detrás de un proxy que no conserve `Host` pueda salir."""
    origen = request.headers.get("origin") or request.headers.get("referer") or "ninguno"
    detalle = (
        f"Origen no permitido: la petición viene de «{html.escape(origen)}» y este "
        "servidor solo acepta peticiones desde sí mismo. Si accedes tras un proxy "
        "inverso, define BASE_URL en el .env (o en Ajustes) con tu dominio."
    )
    return _respuesta_403(detalle, request)


def _respuesta_host_rechazado(request: Request) -> Response:
    """403 específico del `Host`, con el nombre recibido y cómo permitirlo.

    Va aparte del de origen porque la salida es distinta: aquí el problema es
    que el `Host` no está en la lista, y la solución es `ALLOWED_HOSTS` (no hace
    falta una URL completa como con `base_url`)."""
    host = request.headers.get("host", "")
    detalle = (
        f"Host no permitido: «{html.escape(host)}». Este servidor solo acepta "
        "peticiones dirigidas a localhost, a una IP de su red, al dominio de "
        "BASE_URL o a un nombre de ALLOWED_HOSTS. Si entras por el nombre del "
        "equipo (por ejemplo «raspberrypi.local»), añádelo a ALLOWED_HOSTS en el .env."
    )
    return _respuesta_403(detalle, request)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


async def hash_password_async(password: str) -> str:
    """`hash_password` es CPU-bound (PBKDF2): corre en el ejecutor propio para no
    bloquear el bucle de eventos — mismo criterio que `verify_password`."""
    loop = asyncio.get_running_loop()
    async with _pbkdf2_sem:
        return await loop.run_in_executor(_ejecutor_pbkdf2(), hash_password, password)


def necesita_rehash(stored: str) -> bool:
    """True si el hash guardado se calculó con MENOS iteraciones que las actuales
    (p. ej. uno de antes de subir el contador). Se rehashea al iniciar sesión,
    cuando ya se tiene la contraseña en claro — y SIN tocar
    `auth_session_version`: subir iteraciones no debe cerrar sesiones."""
    try:
        _, iterations, _, _ = stored.split("$")
        return int(iterations) < _PBKDF2_ITERATIONS
    except (ValueError, AttributeError):
        return False


async def verify_password(password: str, stored: str) -> bool:
    """Nunca revienta con un stored malformado/vacío — un hash aún sin
    configurar simplemente no valida ninguna contraseña.

    El PBKDF2 corre en el ejecutor propio (fuera del bucle de eventos de la Pi),
    acotado por el semáforo para que una ráfaga no agote los hilos."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    loop = asyncio.get_running_loop()
    async with _pbkdf2_sem:
        actual = await loop.run_in_executor(
            _ejecutor_pbkdf2(),
            hashlib.pbkdf2_hmac, "sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


@functools.lru_cache(maxsize=1)
def _hash_de_relleno() -> str:
    """Hash de relleno, nunca de una contraseña real — sirve solo para que
    `verify_password` pague siempre el mismo coste de PBKDF2 aunque todavía no
    haya ningún `auth_password_hash` guardado.

    Perezoso a propósito: calcularlo en la importación (600.000 o 260.000
    iteraciones) penalizaba cada arranque y cada módulo de prueba que importa
    `auth`. Con `lru_cache` se calcula una vez, la primera vez que se usa."""
    return hash_password(secrets.token_hex(32))


async def credenciales_validas(username: str, password: str, settings: Settings) -> bool:
    """Encontrado en revisión (timing side-channel): antes, `and` cortaba
    en cuanto auth_password_hash/auth_username estaban vacíos o el
    usuario no coincidía, así que verify_password() (PBKDF2, cara)
    NUNCA se ejecutaba en esos casos — solo en un intento con usuario
    correcto y contraseña incorrecta. Medir cuánto tarda la respuesta
    habría bastado para distinguir "el modo no tiene contraseña puesta"
    o "ese usuario no existe" de "contraseña incorrecta", sin necesidad
    de ver el resultado. Ahora verify_password() se llama SIEMPRE que el
    modo pueda requerirla (contra el hash real o, si no hay ninguno
    guardado, contra uno de relleno) antes de combinar con el resto de
    condiciones — el coste de PBKDF2 es el mismo se acierte o no.

    El usuario se compara en bytes UTF-8: `hmac.compare_digest` no admite
    `str` no-ASCII y un nombre con tilde/ñ reventaría con TypeError."""
    if settings.auth_mode == "password":
        password_ok = await verify_password(
            password, settings.auth_password_hash or _hash_de_relleno())
        return bool(settings.auth_password_hash) and password_ok
    if settings.auth_mode == "user_password":
        password_ok = await verify_password(
            password, settings.auth_password_hash or _hash_de_relleno())
        usuario_ok = hmac.compare_digest(
            username.encode("utf-8"), settings.auth_username.encode("utf-8"))
        return (
            bool(settings.auth_username) and bool(settings.auth_password_hash)
            and usuario_ok and password_ok
        )
    return False


def sign_token(payload: str, secret: str) -> str:
    """HMAC-SHA256 sobre una cadena cualquiera — primitiva genérica,
    reutilizada tanto por la cookie de sesión de aquí como por el token
    de candidato de D10 (services/orchestrator.py::crear_token_candidato).
    Sin JWT ni dependencias nuevas (CLAUDE.md §2): un payload + una firma,
    separados por un punto."""
    mac = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def verify_token(token: str, secret: str) -> str | None:
    """Devuelve el payload si la firma es válida, None si no — nunca
    revienta con un token ausente/malformado."""
    try:
        payload, mac = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload if hmac.compare_digest(mac, expected) else None


def crear_cookie_sesion(secret: str, version: int = 0) -> str:
    """Payload `emitida_en.version`, firmado con `secret`.

    La versión ata la cookie al estado de las credenciales: al cambiarlas sube y
    las cookies emitidas antes dejan de valer. Una cookie del formato viejo (solo
    el timestamp, sin versión) tampoco vale — fuerza un inicio de sesión nuevo."""
    return sign_token(f"{int(time.time())}.{version}", secret)


def sesion_valida(token: str | None, secret: str, version_actual: int = 0) -> bool:
    if not token or not secret:
        return False
    payload = verify_token(token, secret)
    if payload is None:
        return False
    try:
        emitida_en_str, _, version_str = payload.partition(".")
        emitida_en = int(emitida_en_str)
        version = int(version_str)
    except ValueError:
        # Formato viejo (sin versión) o corrupto.
        return False
    if version != version_actual:
        return False
    return (time.time() - emitida_en) < SESSION_MAX_AGE


async def _basic_auth_valido(request: Request, settings: Settings) -> bool:
    cabecera = request.headers.get("authorization", "")
    if not cabecera.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(cabecera[6:]).decode("utf-8")
        usuario, _, password = decoded.partition(":")
    except Exception:
        return False
    return await credenciales_validas(usuario, password, settings)


class AuthMiddleware(BaseHTTPMiddleware):
    """Dos trabajos: (1) la comprobación de Origen/Host para los métodos que
    cambian estado, que corre SIEMPRE (también con `auth_mode="none"`); y (2) la
    autenticación por cookie/Basic, que es no-op con `auth_mode="none"`."""

    async def dispatch(self, request: Request, call_next):
        # E6: arranque degradado — con configuración/credenciales desconocidas
        # se falla cerrado y solo se sirve diagnóstico.
        if getattr(request.app.state, "db_degraded", False):
            path = request.url.path
            if path in _RUTAS_DIAGNOSTICO or path.startswith(_PREFIJOS_EXENTOS):
                return await call_next(request)
            if path.startswith("/api/"):
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Base de datos no disponible — consulta /api/health"},
                )
            return HTMLResponse(
                "<h1>Base de datos no lista</h1>"
                "<p>El arranque no pudo conectar con PostgreSQL o el esquema no está migrado. "
                '<a href="/estado">Consulta el estado del sistema</a>.</p>',
                status_code=503,
            )

        settings = get_settings()

        # CSRF/Origen: corre ANTES de cualquier short-circuit de auth, porque
        # /login (exenta) también es un POST de estado y no debe aceptarse
        # cross-site. Vale para todos los auth_mode.
        if request.method in _METODOS_DE_ESTADO and _peticion_cross_site(request, settings):
            return _respuesta_origen_rechazado(request)

        if settings.auth_mode == "none":
            # DNS rebinding: sin contraseña no hay cookie que defender, y un
            # rebinding permite LEER respuestas (GET incluidos), así que el Host
            # se valida en TODOS los métodos. El healthcheck va por localhost /
            # 127.0.0.1 (IP literal) y pasa.
            if _host_no_permitido(request, settings):
                return _respuesta_host_rechazado(request)
            return await call_next(request)

        path = request.url.path
        if path in _RUTAS_EXENTAS or path.startswith(_PREFIJOS_EXENTOS):
            return await call_next(request)

        if sesion_valida(request.cookies.get(COOKIE_NAME), settings.secret_key,
                         settings.auth_session_version):
            return await call_next(request)
        if await _basic_auth_valido(request, settings):
            return await call_next(request)

        if path.startswith("/api/"):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="ZascArr"'})

        query = f"?{request.url.query}" if request.url.query else ""
        siguiente = f"{path}{query}"
        # `next` va como valor de query: sin codificar, un `&` de la query
        # original se parsea como parámetro aparte y trunca el destino.
        return RedirectResponse(f"/login?next={quote(siguiente, safe='')}", status_code=303)
