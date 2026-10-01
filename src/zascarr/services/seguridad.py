"""Seguridad de acceso: la regla de contraseña y su guardado, en un solo sitio.

Antes esta lógica vivía dentro del router de Ajustes (`web/ajustes.py`). A11
necesita la MISMA regla desde el instalador (`python -m zascarr.cli.seguridad`):
duplicarla habría dejado dos mínimos de longitud que tarde o temprano divergen
(CLAUDE.md §3.1: la capa de servicios es la única fuente de verdad del negocio).
El router y el comando son ahora finos y comparten `fijar_seguridad`.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.services.auth import hash_password_async, limpiar_cache_basic
from zascarr.services.runtime_settings import RuntimeSettingsService

MODOS = ("none", "password", "user_password")

# Longitud (OWASP): sin segundo factor, una contraseña corta cae rápido aun con
# el retraso progresivo. 15 es lo recomendado; 12 es el mínimo duro.
# `scripts/_exposicion.sh` repite el mínimo para no fallar tarde en el instalador;
# `tests/test_exposicion.py` comprueba que las dos cifras son la misma.
LONGITUD_MINIMA = 12
LONGITUD_RECOMENDADA = 15

MENSAJE_CORTA = (
    f"La contraseña debe tener al menos {LONGITUD_MINIMA} caracteres. Mejor una frase "
    "larga que recuerdes (por ejemplo, tres o cuatro palabras)."
)
MENSAJE_DEBIL = (
    f"Contraseña corta: menos de {LONGITUD_RECOMENDADA} caracteres se considera débil "
    "sin un segundo factor. Una frase más larga es más segura."
)
MENSAJE_SIN_CONTRASENA = (
    "Pon una contraseña antes de activar este modo — si no, no podrás volver a entrar."
)
MENSAJE_SIN_USUARIO = "Este modo necesita también un nombre de usuario."


@dataclass
class ResultadoSeguridad:
    #: Mensaje para el coleccionista si NO se guardó nada.
    error: str | None = None
    #: Aviso que acompaña a un guardado correcto (p. ej. contraseña corta).
    aviso: str | None = None
    #: ¿Cambió contraseña, usuario o modo? Quien llama debe re-emitir la cookie.
    cambia_credenciales: bool = False


def validar_contrasena(password: str) -> tuple[str | None, str | None]:
    """(error, aviso) de una contraseña NUEVA. Una cadena vacía no se valida:
    significa «no cambiar la contraseña»."""
    if not password:
        return None, None
    if len(password) < LONGITUD_MINIMA:
        return MENSAJE_CORTA, None
    if len(password) < LONGITUD_RECOMENDADA:
        return None, MENSAJE_DEBIL
    return None, None


def url_publica_valida(url: str) -> bool:
    """`https://host[:puerto][/ruta]` — la URL pública de un proxy inverso con TLS.

    Solo `https`: con `http` el proxy no estaría haciendo de frontera segura.
    `scripts/_exposicion.sh::url_publica_valida` aplica la misma regla en el instalador.
    """
    try:
        partes = urlsplit(url)
    except ValueError:
        return False
    return partes.scheme == "https" and bool(partes.hostname)


async def fijar_seguridad(
    db: AsyncSession, *, modo: str, usuario: str, password: str, base_url: str,
) -> ResultadoSeguridad:
    """Guarda modo, usuario, contraseña (hasheada) y `base_url`.

    `password` vacío = conservar la que ya hay. Nunca deja la app en un modo que
    nadie pueda desbloquear (A6): activar contraseña sin ninguna —ni recién
    escrita ni ya guardada— se rechaza en vez de dejar al coleccionista fuera de
    su propia instalación.
    """
    if modo not in MODOS:
        raise ValueError(f"modo de autenticación no reconocido: {modo!r}")

    settings = get_settings()
    if modo in ("password", "user_password") and not password and not settings.auth_password_hash:
        return ResultadoSeguridad(error=MENSAJE_SIN_CONTRASENA)
    if modo == "user_password" and not usuario and not settings.auth_username:
        return ResultadoSeguridad(error=MENSAJE_SIN_USUARIO)

    error, aviso = validar_contrasena(password)
    if error:
        return ResultadoSeguridad(error=error)

    cambios: dict = {"auth_mode": modo, "auth_username": usuario, "base_url": base_url.rstrip("/")}
    # Cambiar contraseña, usuario o modo sube la versión de sesión: las cookies
    # emitidas antes dejan de valer. El rehasheo por iteraciones NO la sube.
    cambia = (
        modo != settings.auth_mode
        or usuario != settings.auth_username
        or bool(password)
    )
    if password:
        cambios["auth_password_hash"] = await hash_password_async(password)
    if cambia:
        cambios["auth_session_version"] = settings.auth_session_version + 1
    await RuntimeSettingsService(db).save(cambios)
    if cambia:
        # La caché de aciertos de Basic Auth queda inservible al cambiar las
        # credenciales: sus entradas viejas no deben seguir dando acceso.
        limpiar_cache_basic()
    return ResultadoSeguridad(aviso=aviso, cambia_credenciales=cambia)
