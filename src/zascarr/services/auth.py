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
import hashlib
import hmac
import secrets
import time
from urllib.parse import quote

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from zascarr.config import Settings, get_settings

COOKIE_NAME = "zascarr_session"
# 30 días: es una herramienta de un solo operador en su propia Pi, no un
# panel bancario — pedir la contraseña en cada visita sería fricción sin
# beneficio real de seguridad aquí.
SESSION_MAX_AGE = 30 * 24 * 3600
# OWASP (2023) recomendaba 260.000; la cifra vigente para PBKDF2-HMAC-SHA256 es
# 600.000. El hash guarda su número de iteraciones, así que subirlo no rompe los
# hashes viejos: se regeneran al iniciar sesión.
_PBKDF2_ITERATIONS = 600_000

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


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


async def verify_password(password: str, stored: str) -> bool:
    """Nunca revienta con un stored malformado/vacío — un hash aún sin
    configurar simplemente no valida ninguna contraseña.

    El PBKDF2 corre en un hilo (`to_thread`): 600.000 iteraciones en el bucle de
    eventos de la Pi congelarían las peticiones que vienen detrás."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    actual = await asyncio.to_thread(
        hashlib.pbkdf2_hmac, "sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


# Hash de relleno, nunca de una contraseña real — sirve solo para que
# verify_password() pague siempre el mismo coste de PBKDF2 (~260.000
# iteraciones) aunque todavía no haya ningún auth_password_hash guardado.
_HASH_DE_RELLENO = hash_password(secrets.token_hex(32))


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
            password, settings.auth_password_hash or _HASH_DE_RELLENO)
        return bool(settings.auth_password_hash) and password_ok
    if settings.auth_mode == "user_password":
        password_ok = await verify_password(
            password, settings.auth_password_hash or _HASH_DE_RELLENO)
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


def crear_cookie_sesion(secret: str) -> str:
    return sign_token(str(int(time.time())), secret)


def sesion_valida(token: str | None, secret: str) -> bool:
    if not token or not secret:
        return False
    payload = verify_token(token, secret)
    if payload is None:
        return False
    try:
        emitida_en = int(payload)
    except ValueError:
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
    """No-op en cuanto `auth_mode == "none"` (el valor por defecto) — la
    suite de tests existente, que nunca configura autenticación, no ve
    ningún cambio de comportamiento."""

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
        if settings.auth_mode == "none":
            return await call_next(request)

        path = request.url.path
        if path in _RUTAS_EXENTAS or path.startswith(_PREFIJOS_EXENTOS):
            return await call_next(request)

        if sesion_valida(request.cookies.get(COOKIE_NAME), settings.secret_key):
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
