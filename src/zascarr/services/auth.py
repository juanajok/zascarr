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

import base64
import hashlib
import hmac
import secrets
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from zascarr.config import Settings, get_settings

COOKIE_NAME = "zascarr_session"
# 30 días: es una herramienta de un solo operador en su propia Pi, no un
# panel bancario — pedir la contraseña en cada visita sería fricción sin
# beneficio real de seguridad aquí.
SESSION_MAX_AGE = 30 * 24 * 3600
_PBKDF2_ITERATIONS = 260_000  # recomendación OWASP (2023) para PBKDF2-SHA256

# Rutas alcanzables sin sesión ni Basic Auth incluso con auth_mode activo:
# /login (si no, nadie podría autenticarse nunca — bucle de redirección),
# /api/health (los healthchecks de Docker/monitorización no llevan
# credenciales), estáticos y el propio aviso legal (texto informativo,
# no hay nada que proteger ahí).
_RUTAS_EXENTAS = {"/login", "/api/health", "/legal", "/favicon.ico"}
_PREFIJOS_EXENTOS = ("/static/",)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Nunca revienta con un stored malformado/vacío — un hash aún sin
    configurar simplemente no valida ninguna contraseña."""
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (ValueError, AttributeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


# Hash de relleno, nunca de una contraseña real — sirve solo para que
# verify_password() pague siempre el mismo coste de PBKDF2 (~260.000
# iteraciones) aunque todavía no haya ningún auth_password_hash guardado.
_HASH_DE_RELLENO = hash_password(secrets.token_hex(32))


def credenciales_validas(username: str, password: str, settings: Settings) -> bool:
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
    condiciones — el coste de PBKDF2 es el mismo se acierte o no."""
    if settings.auth_mode == "password":
        password_ok = verify_password(password, settings.auth_password_hash or _HASH_DE_RELLENO)
        return bool(settings.auth_password_hash) and password_ok
    if settings.auth_mode == "user_password":
        password_ok = verify_password(password, settings.auth_password_hash or _HASH_DE_RELLENO)
        usuario_ok = hmac.compare_digest(username, settings.auth_username)
        return (
            bool(settings.auth_username) and bool(settings.auth_password_hash)
            and usuario_ok and password_ok
        )
    return False


def _sign(payload: str, secret: str) -> str:
    mac = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def _verify(token: str, secret: str) -> str | None:
    try:
        payload, mac = token.rsplit(".", 1)
    except ValueError:
        return None
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return payload if hmac.compare_digest(mac, expected) else None


def crear_cookie_sesion(secret: str) -> str:
    return _sign(str(int(time.time())), secret)


def sesion_valida(token: str | None, secret: str) -> bool:
    if not token or not secret:
        return False
    payload = _verify(token, secret)
    if payload is None:
        return False
    try:
        emitida_en = int(payload)
    except ValueError:
        return False
    return (time.time() - emitida_en) < SESSION_MAX_AGE


def _basic_auth_valido(request: Request, settings: Settings) -> bool:
    cabecera = request.headers.get("authorization", "")
    if not cabecera.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(cabecera[6:]).decode("utf-8")
        usuario, _, password = decoded.partition(":")
    except Exception:
        return False
    return credenciales_validas(usuario, password, settings)


class AuthMiddleware(BaseHTTPMiddleware):
    """No-op en cuanto `auth_mode == "none"` (el valor por defecto) — la
    suite de tests existente, que nunca configura autenticación, no ve
    ningún cambio de comportamiento."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if settings.auth_mode == "none":
            return await call_next(request)

        path = request.url.path
        if path in _RUTAS_EXENTAS or path.startswith(_PREFIJOS_EXENTOS):
            return await call_next(request)

        if sesion_valida(request.cookies.get(COOKIE_NAME), settings.secret_key):
            return await call_next(request)
        if _basic_auth_valido(request, settings):
            return await call_next(request)

        if path.startswith("/api/"):
            return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="ZascArr"'})

        query = f"?{request.url.query}" if request.url.query else ""
        siguiente = f"{path}{query}"
        return RedirectResponse(f"/login?next={siguiente}", status_code=303)
