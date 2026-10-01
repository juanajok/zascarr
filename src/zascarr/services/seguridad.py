"""Seguridad de acceso: la regla de contraseña y su guardado, en un solo sitio.

Antes esta lógica vivía dentro del router de Ajustes (`web/ajustes.py`). A11
necesita la MISMA regla desde el instalador (`python -m zascarr.cli.seguridad`):
duplicarla habría dejado dos mínimos de longitud que tarde o temprano divergen
(CLAUDE.md §3.1: la capa de servicios es la única fuente de verdad del negocio).
El router y el comando son ahora finos y comparten `fijar_seguridad`.
"""
from __future__ import annotations

import re
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


#: Nombres de host que cuentan como «esta máquina» (para bind y para BASE_URL).
_LOCALES = {"127.0.0.1", "localhost", "::1"}

EXPOSICION_LOCAL = "local"
EXPOSICION_RED = "red"
EXPOSICION_PROXY = "proxy"

AVISO_EXPUESTA_SIN_CONTRASENA = {
    EXPOSICION_RED: (
        "ZascArr está abierto a tu red local y no tiene contraseña: cualquier "
        "dispositivo de la red puede usarlo. Pon una en Ajustes → Seguridad."
    ),
    EXPOSICION_PROXY: (
        "Hay una dirección pública configurada para ZascArr y no tiene contraseña: "
        "cualquiera que llegue a ella puede usarlo. Pon una en Ajustes → Seguridad."
    ),
}


def exposicion_efectiva(settings=None) -> str:
    """Hasta dónde puede llegar la interfaz, según cómo se publicó (A11).

    - `red`: el equipo publica el puerto fuera de localhost (`0.0.0.0` u otra IP).
    - `proxy`: el puerto sigue en localhost pero hay una `BASE_URL` que no es local,
      es decir, un proxy inverso la expone.
    - `local`: solo esta máquina.

    La app no controla su puerto: esto solo refleja lo que el instalador escribió.
    """
    s = settings or get_settings()
    bind = (s.zascarr_bind_address or "").strip().strip("[]").lower()
    if bind not in _LOCALES:
        return EXPOSICION_RED
    host = (urlsplit(s.base_url).hostname or "").lower() if s.base_url else ""
    if host and host not in _LOCALES:
        return EXPOSICION_PROXY
    return EXPOSICION_LOCAL


def hay_contrasena(settings=None) -> bool:
    """Contraseña efectiva: modo con contraseña y hash guardado. Es el mismo
    criterio con el que el middleware decide si exige credenciales."""
    s = settings or get_settings()
    return s.auth_mode in ("password", "user_password") and bool(s.auth_password_hash)


def aviso_de_exposicion(settings=None) -> str | None:
    """Texto para `/api/health` si la interfaz está abierta y sin contraseña."""
    s = settings or get_settings()
    nivel = exposicion_efectiva(s)
    if nivel == EXPOSICION_LOCAL or hay_contrasena(s):
        return None
    return AVISO_EXPUESTA_SIN_CONTRASENA[nivel]


def estado_de_seguridad(settings=None) -> dict:
    """Estado de seguridad estructurado, SEPARADO de la salud técnica.

    `status` de `/api/health` sigue diciendo si el servicio funciona; esto dice si
    conviene prestarle atención. Una interfaz abierta y sin contraseña no es un
    servicio caído, pero tampoco algo que deba pasar desapercibido: quien pinte el
    estado puede mostrar «Atención» sin confundirlo con «inaccesible».
    """
    s = settings or get_settings()
    nivel = exposicion_efectiva(s)
    contrasena = hay_contrasena(s)
    return {
        "exposicion": nivel,
        "contrasena": contrasena,
        "atencion": nivel != EXPOSICION_LOCAL and not contrasena,
    }


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


# `https://host[:puerto]`, y NADA más: sin ruta (ZascArr no está probado bajo un
# prefijo, así que aceptarlo prometería algo sin demostrar), sin usuario, sin IPv6.
_URL_PUBLICA = re.compile(r"https://([^/:@\s]+)(?::([0-9]{1,5}))?")
_ETIQUETA_DNS = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_OCTETO = re.compile(r"0|[1-9][0-9]{0,2}")


def url_publica_valida(url: str) -> bool:
    """La URL pública de un proxy inverso con TLS: `https://dominio[:puerto]`.

    - Solo `https`: con `http` el proxy no estaría haciendo de frontera segura.
    - Sin ruta: no hay soporte probado para colgar ZascArr de un prefijo.
    - Puerto en 1–65535. Host ASCII (un dominio internacionalizado va en punycode,
      que es lo que el navegador envía en `Origin`).
    - Si el último tramo es numérico el host tiene que ser una IPv4 de verdad
      (cuatro octetos 0–255): `999.1.1.1` o `1.2.3` no son dominios ni direcciones.
    - Sin direcciones IPv6 entre corchetes (no se validan; un dominio las cubre).

    `scripts/_exposicion.sh::url_publica_valida` aplica la MISMA regla en el
    instalador; `tests/test_exposicion_bash.py` las compara con los mismos casos.
    """
    m = _URL_PUBLICA.fullmatch(url)
    if not m:
        return False
    host, puerto = m.groups()
    if puerto is not None and not 1 <= int(puerto) <= 65535:
        return False
    if len(host) > 253:
        return False
    etiquetas = host.split(".")
    if not all(_ETIQUETA_DNS.fullmatch(e) for e in etiquetas):
        return False
    if etiquetas[-1].isdigit():
        return len(etiquetas) == 4 and all(
            _OCTETO.fullmatch(e) and int(e) <= 255 for e in etiquetas)
    return True


async def fijar_seguridad(
    db: AsyncSession, *, modo: str, usuario: str, password: str, base_url: str | None,
) -> ResultadoSeguridad:
    """Guarda modo, usuario, contraseña (hasheada) y `base_url`.

    `password` vacío = conservar la que ya hay. `base_url=None` = no tocar la que
    haya (el formulario de Ajustes pasa siempre una cadena, y vacía significa «vuelve
    al valor del `.env`»; el instalador no debe pisar lo que se puso en Ajustes).
    Nunca deja la app en un modo que
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

    cambios: dict = {"auth_mode": modo, "auth_username": usuario}
    if base_url is not None:
        cambios["base_url"] = base_url.rstrip("/")
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
