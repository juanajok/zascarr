# ruff: noqa: E501
"""Seguridad de acceso: la regla de contraseña y su guardado, en un solo sitio.

Antes esta lógica vivía dentro del router de Ajustes (`web/ajustes.py`). A11
necesita la MISMA regla desde el instalador (`python -m zascarr.cli.seguridad`):
duplicarla habría dejado dos mínimos de longitud que tarde o temprano divergen
(CLAUDE.md §3.1: la capa de servicios es la única fuente de verdad del negocio).
El router y el comando son ahora finos y comparten `fijar_seguridad`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.services.auth import hash_password_async, limpiar_cache_basic
from zascarr.services.reautenticacion import Reauth, comprobar_contrasena_actual
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
# BL-OPS3 (#456): cambiar cómo se entra exige la contraseña actual. Textos fijos, sin repetir lo escrito.
MENSAJE_FALTA_ACTUAL = (
    "Para cambiar esto, escribe tu contraseña actual. Si no ves el campo, recarga la página."
)
MENSAJE_ACTUAL_INCORRECTA = "La contraseña actual no es correcta."
MENSAJE_COLA_LLENA = "ZascArr está ocupado. Espera unos segundos e inténtalo otra vez."
MENSAJE_NO_COINCIDEN = "Las dos contraseñas nuevas no coinciden."
_MENSAJE_BLOQUEADA = (
    "Has fallado la contraseña varias veces. Por seguridad, no se pueden cambiar estos ajustes hasta "
    "las {hora}. Puedes seguir usando ZascArr con normalidad. Si la has olvidado, quien instaló ZascArr "
    "puede poner una nueva."
)
#: Qué se ha cambiado (para el registro, nunca los valores).
CAMBIO_CONTRASENA, CAMBIO_MODO, CAMBIO_USUARIO, CAMBIO_DIRECCION = (
    "contrasena", "modo", "usuario", "direccion")


def mensaje_bloqueada(hasta_epoch: float) -> str:
    """El aviso de bloqueo, con la hora de fin en la zona horaria del servidor (`TZ`)."""
    return _MENSAJE_BLOQUEADA.format(hora=time.strftime("%H:%M", time.localtime(hasta_epoch)))


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


def base_url_es_publica(base_url: str | None) -> bool:
    """¿Esa `BASE_URL` apunta a algo que no es esta máquina?

    Deliberadamente LAXA: acepta `http://`, subrutas y lo que `urlsplit` entienda. Sirve
    para decidir qué hay que LIMPIAR de una configuración histórica; el validador
    estricto (`url_publica_valida`) es solo para lo que se acepta de nuevo.
    """
    host = (urlsplit(base_url).hostname or "").lower() if base_url else ""
    return bool(host) and host not in _LOCALES


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
    if base_url_es_publica(s.base_url):
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
    #: BL-OPS3: por qué se rechazó por la contraseña actual (`falta_actual`, `actual_incorrecta`,
    #: `bloqueada`, `ocupada`); `None` si no fue por eso. Es lo que registra el router (sin valores).
    motivo_rechazo: str | None = None
    #: BL-OPS3: qué cambió en un guardado aplicado (subconjunto de `CAMBIO_*`).
    cambios: tuple[str, ...] = ()


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


def _direccion_normalizada(base_url: str | None) -> str:
    return (base_url or "").rstrip("/")


def _cambios_pedidos(settings, *, modo: str, usuario: str, password: str,
                     base_url: str | None) -> tuple[str, ...]:
    """Qué de lo guardado cambiaría este envío (sin valores). `base_url=None` no la toca; las dos
    direcciones se normalizan con `rstrip("/")`: un `BASE_URL` del `.env` con «/» final no cuenta
    como cambio al guardar el mismo valor."""
    cambios = []
    if password:
        cambios.append(CAMBIO_CONTRASENA)
    if modo != settings.auth_mode:
        cambios.append(CAMBIO_MODO)
    if usuario != settings.auth_username:
        cambios.append(CAMBIO_USUARIO)
    if base_url is not None and _direccion_normalizada(base_url) != _direccion_normalizada(settings.base_url):
        cambios.append(CAMBIO_DIRECCION)
    return tuple(cambios)


def exige_contrasena_actual(settings, *, modo: str, usuario: str, password: str,
                            base_url: str | None) -> bool:
    """¿Este envío pide la contraseña actual? (BL-OPS3, FR-01.) `True` si y solo si hay contraseña en vigor
    y cambia algo que podría debilitar o secuestrar el acceso: contraseña nueva, modo, usuario o dirección
    pública. Activar la contraseña por primera vez (no hay «actual»), guardar sin cambios y conservar la
    contraseña en blanco no la piden. Es la ÚNICA fuente de la regla: el router no la repite."""
    return hay_contrasena(settings) and bool(
        _cambios_pedidos(settings, modo=modo, usuario=usuario, password=password, base_url=base_url))


def _comprobar_forma(
    settings, *, modo: str, usuario: str, password: str, password_repetida: str | None,
) -> tuple[ResultadoSeguridad | None, str | None]:
    """Las reglas de FORMA, que no dependen de secretos: modo conocido, contraseña y usuario obligatorios,
    longitud y repetición de la nueva. `(rechazo, aviso)`: un rechazo no gasta intentos de contraseña."""
    if modo not in MODOS:
        raise ValueError(f"modo de autenticación no reconocido: {modo!r}")
    if modo in ("password", "user_password") and not password and not settings.auth_password_hash:
        return ResultadoSeguridad(error=MENSAJE_SIN_CONTRASENA), None
    if modo == "user_password" and not usuario and not settings.auth_username:
        return ResultadoSeguridad(error=MENSAJE_SIN_USUARIO), None
    error, aviso = validar_contrasena(password)
    if error:
        return ResultadoSeguridad(error=error), None
    if password and password_repetida is not None and password != password_repetida:
        return ResultadoSeguridad(error=MENSAJE_NO_COINCIDEN), None
    return None, aviso


async def _comprobar_actual(
    settings, *, modo: str, usuario: str, password: str, base_url: str | None, contrasena_actual: str,
) -> ResultadoSeguridad | None:
    """La contraseña ACTUAL, si este envío la exige. `None` = puede seguir; si no, el rechazo (no se
    guarda nada, no se sube la versión y no se vacía ninguna caché)."""
    if not exige_contrasena_actual(settings, modo=modo, usuario=usuario, password=password,
                                   base_url=base_url):
        return None
    if not contrasena_actual:
        return ResultadoSeguridad(error=MENSAJE_FALTA_ACTUAL, motivo_rechazo="falta_actual")
    reauth = await comprobar_contrasena_actual(contrasena_actual, settings)
    if reauth.resultado is Reauth.OK:
        return None
    if reauth.resultado is Reauth.BLOQUEADA:
        return ResultadoSeguridad(error=mensaje_bloqueada(reauth.hasta_epoch or 0.0),
                                  motivo_rechazo="bloqueada")
    if reauth.resultado is Reauth.OCUPADA:
        return ResultadoSeguridad(error=MENSAJE_COLA_LLENA, motivo_rechazo="ocupada")
    return ResultadoSeguridad(error=MENSAJE_ACTUAL_INCORRECTA, motivo_rechazo="actual_incorrecta")


async def _guardar_seguridad(
    db: AsyncSession, settings, *, modo: str, usuario: str, password: str, base_url: str | None,
    aviso: str | None,
) -> ResultadoSeguridad:
    """El ÚNICO punto que escribe modo, usuario, contraseña y dirección. Es privado: lo llaman solo las
    dos funciones públicas, cada una tras sus comprobaciones (una prueba estática lo exige). No hay un
    parámetro que salte la comprobación de la contraseña actual: esa decisión es de quien llama, y
    `fijar_seguridad` la toma siempre."""
    cambios_pedidos = _cambios_pedidos(settings, modo=modo, usuario=usuario, password=password,
                                       base_url=base_url)
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
    return ResultadoSeguridad(aviso=aviso, cambia_credenciales=cambia, cambios=cambios_pedidos)


async def fijar_seguridad(
    db: AsyncSession, *, modo: str, usuario: str, password: str, base_url: str | None,
    contrasena_actual: str = "", password_repetida: str | None = None,
) -> ResultadoSeguridad:
    """Guarda modo, usuario, contraseña (hasheada) y `base_url`: la vía de la WEB.

    Con una contraseña en vigor, cualquier cambio que pueda debilitar o secuestrar el acceso exige
    `contrasena_actual` (ver `exige_contrasena_actual`). `password` vacío = conservar la que ya hay.
    `password_repetida`, si no es `None`, debe coincidir con `password` (el formulario de Ajustes la
    pide). `base_url=None` = no tocar la que haya (el formulario de Ajustes pasa siempre una cadena, y
    vacía significa «vuelve al valor del `.env`»). Nunca deja la app en un modo que nadie pueda
    desbloquear (A6): activar contraseña sin ninguna —ni recién escrita ni ya guardada— se rechaza en
    vez de dejar al coleccionista fuera de su propia instalación."""
    settings = get_settings()
    rechazo, aviso = _comprobar_forma(
        settings, modo=modo, usuario=usuario, password=password, password_repetida=password_repetida)
    if rechazo:
        return rechazo
    rechazo = await _comprobar_actual(
        settings, modo=modo, usuario=usuario, password=password, base_url=base_url,
        contrasena_actual=contrasena_actual)
    if rechazo:
        return rechazo
    return await _guardar_seguridad(db, settings, modo=modo, usuario=usuario, password=password,
                                    base_url=base_url, aviso=aviso)


async def fijar_seguridad_desde_el_equipo(
    db: AsyncSession, *, modo: str, usuario: str, password: str, base_url: str | None,
) -> ResultadoSeguridad:
    """Lo mismo que `fijar_seguridad` SIN pedir la contraseña actual: solo para `cli/seguridad.py` (el
    instalador, que corre en el equipo y como root, y es la vía de recuperación si se olvida la
    contraseña). Con dos funciones de nombre distinto, y no un booleano que salte la comprobación, una
    revisión o un `grep` ven quién la usa (hay una prueba que lo exige): el router nunca la importa."""
    settings = get_settings()
    rechazo, aviso = _comprobar_forma(
        settings, modo=modo, usuario=usuario, password=password, password_repetida=None)
    if rechazo:
        return rechazo
    return await _guardar_seguridad(db, settings, modo=modo, usuario=usuario, password=password,
                                    base_url=base_url, aviso=aviso)
