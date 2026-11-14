"""Búfer de los últimos eventos de la aplicación para descargarlos desde la UI.

La app escribe con structlog a stdout y Docker rota esos ficheros en el host; desde
el contenedor no se pueden leer sin montar rutas del host ni abrir una shell. Este
módulo guarda en memoria un número acotado de eventos (sin ficheros, sin base de
datos y sin dependencias nuevas) y los sirve como texto desde /ui/logs.

Privacidad: el texto puede contener rutas y nombres de la biblioteca; se avisa en
la propia pantalla. Además se redactan campos y valores con pinta de credencial
(token, contraseña, clave de API, cookie, autorización) y las queries de URL.
"""
from __future__ import annotations

import re
import threading
import traceback
from collections import deque
from datetime import UTC, datetime
from typing import Any

import structlog

MAX_EVENTOS = 500
MAX_BYTES = 256 * 1024
_SIN_REGISTROS = "No hay registros recientes de la aplicación.\n"

_lock = threading.Lock()
_eventos: deque[dict[str, Any]] = deque(maxlen=MAX_EVENTOS)
_instalado = False

#: Campos cuyo valor no sale del proceso aunque el emisor se olvide de limpiarlo.
_CLAVE_SENSIBLE = re.compile(
    r"(?i)(password|passwd|contrase(?:n|ñ)a|secret|token|api[_-]?key|authorization|cookie|bearer)"
)
#: `https://usuario:clave@host/...` → se conserva el host, no las credenciales.
_USERINFO = re.compile(r"(://)[^/@\s]+@")
#: Parámetros de URL con pinta de secreto.
_QUERY_SENSIBLE = re.compile(
    r"(?i)([?&](?:password|passwd|secret|token|api[_-]?key|access_token|refresh_token)=)[^&\s\"']+"
)
#: `token=...`, `Authorization: Bearer ...` escrito en un mensaje de error.
_CLAVE_EN_TEXTO = re.compile(
    r"(?i)((?:password|passwd|secret|token|api[_-]?key|authorization|cookie)\s*[=:]\s*)"
    r"[^\s,;\"']+"
)


def _texto(valor: Any) -> str:
    """Representación corta y estable de un valor de log, sin escribir objetos raros."""
    if isinstance(valor, str):
        return valor
    if isinstance(valor, (int, float, bool)) or valor is None:
        return str(valor)
    try:
        return repr(valor)
    except Exception:  # noqa: BLE001 — un `__repr__` roto no puede tumbar el log
        return "<valor no representable>"


def _sin_secretos(texto: str) -> str:
    """Redacta credenciales reconocibles sin borrar el contexto útil del evento."""
    texto = _USERINFO.sub(r"\1[redactado]@", texto)
    texto = _QUERY_SENSIBLE.sub(r"\1[redactado]", texto)
    texto = _CLAVE_EN_TEXTO.sub(r"\1[redactado]", texto)
    # Authorization: Bearer <token> cuando la clave no venía como `clave=valor`.
    texto = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[redactado]", texto)
    return texto


def _sanear_campo(clave: str, valor: Any) -> Any:
    if _CLAVE_SENSIBLE.search(clave):
        return "[redactado]"
    if isinstance(valor, str):
        return _sin_secretos(valor)
    if isinstance(valor, dict):
        return {str(k): _sanear_campo(str(k), v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sanear_campo(clave, v) for v in valor]
    return valor


def _excepcion(evento: dict[str, Any]) -> str:
    exc = evento.get("exc_info")
    if not exc:
        return ""
    try:
        if isinstance(exc, tuple):
            return "".join(traceback.format_exception(*exc)).rstrip()
        return _texto(exc)
    except Exception:  # noqa: BLE001
        return "Excepción no representable."


def capturar(_logger: Any, _metodo: str, evento: dict[str, Any]) -> dict[str, Any]:
    """Procesador de structlog: copia el evento saneado al búfer y lo deja pasar.

    Se instala antes del renderizador final, así que recibe el evento estructurado
    (timestamp y nivel incluidos) y no altera la salida normal a stdout.
    """
    try:
        copia = {str(k): _sanear_campo(str(k), v) for k, v in evento.items()}
        with _lock:
            _eventos.append(copia)
    except Exception:  # noqa: BLE001 — un fallo del búfer nunca tumba la petición
        pass
    return evento


def instalar_captura() -> None:
    """Añade `capturar` a la cadena de structlog sin cambiar el formato existente.

    Preserva procesadores, fábrica de logger, wrapper y contexto actuales; solo
    inserta el capturador antes del renderizador final. Idempotente.
    """
    global _instalado
    if _instalado:
        return
    config = structlog.get_config()
    procesadores = list(config.get("processors") or [])
    if not any(getattr(p, "__name__", "") == "capturar" for p in procesadores):
        if procesadores:
            procesadores.insert(len(procesadores) - 1, capturar)
        else:
            procesadores.append(capturar)
        config = dict(config)
        config["processors"] = procesadores
        structlog.configure(**config)
    _instalado = True


def limpiar() -> None:
    """Vacía el búfer (pruebas y diagnóstico); no toca la configuración de structlog."""
    with _lock:
        _eventos.clear()


def _linea(evento: dict[str, Any]) -> str:
    fecha = _texto(evento.get("timestamp") or datetime.now(UTC).isoformat())
    nivel = _texto(evento.get("log_level", "info")).upper()
    nombre = _texto(evento.get("event", "(sin evento)"))
    omitidas = {"timestamp", "log_level", "event", "exc_info"}
    extras = [
        f"{clave}={_texto(valor)}"
        for clave, valor in evento.items()
        if clave not in omitidas
    ]
    linea = f"{fecha} {nivel:<7} {nombre}"
    if extras:
        linea += " " + " ".join(extras)
    excepcion = _excepcion(evento)
    if excepcion:
        linea += "\n" + excepcion
    return _sin_secretos(linea)


def texto_reciente() -> str:
    """Últimos eventos en texto plano, acotados por número y tamaño.

    Si el búfer está vacío devuelve una frase explícita para que el fichero
    descargado explique por qué no hay nada.
    """
    with _lock:
        entradas = list(_eventos)
    if not entradas:
        return _SIN_REGISTROS
    texto = "\n".join(_linea(e) for e in entradas) + "\n"
    datos = texto.encode("utf-8")
    if len(datos) > MAX_BYTES:
        recorte = datos[-MAX_BYTES:].decode("utf-8", errors="replace")
        texto = "(registro recortado a los últimos 256 KiB)\n" + recorte
    return texto


__all__ = ["capturar", "instalar_captura", "limpiar", "texto_reciente"]
