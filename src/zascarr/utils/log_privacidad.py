"""SEC-LOG (#369): lo que nunca debe acabar en un registro estructurado.

Política única: de una ruta se registra la categoría (`[ruta]`), de un archivo
su categoría (`[archivo]`), de una URL `[url]`; de una excepción, su tipo. Un
identificador (`file_id`, `operacion`, `hash` corto) sí es diagnóstico y no
identifica la colección. `sanear_evento` es la red de seguridad para stdout y
para el búfer de logs; las llamadas concretas usan además estos ayudantes para
que las pruebas con `structlog` capturado también queden limpias.
"""
from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import urlsplit

RUTA = "[ruta]"
ARCHIVO = "[archivo]"
URL = "[url]"
ERROR = "[error]"

_CLAVES_ARCHIVO = {"archivo", "archivos", "file", "files"}
_CLAVES_RUTA = {
    "path", "paths", "ruta", "rutas", "dir", "directorio", "root", "raiz",
    "carpeta", "destino", "origen_ruta",
}
_CLAVES_URL = {"url", "uri", "enlace", "href", "feed_url"}
_CLAVES_TEXTO = {"error", "motivo", "causa", "detalle", "mensaje"}

#: Rutas absolutas POSIX/Windows y URLs; se sustituyen enteras, no solo el host.
_RUTA_ABSOLUTA = re.compile(
    r"(?<![\w:/])(?:/(?:[^\s\"'<>|]+/)*[^\s\"'<>|]+|[A-Za-z]:\\(?:[^\s\"'<>|]+\\)*[^\s\"'<>|]+)")
_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def _url_sin_datos(match: re.Match[str]) -> str:
    """Conserva el host (diagnóstico) y elimina credenciales, ruta y query."""
    try:
        partes = urlsplit(match.group(0))
        host = partes.netloc.rsplit("@", 1)[-1]
        return f"{partes.scheme}://{host}" if host else URL
    except ValueError:
        return URL


def sanear_texto(texto: str) -> str:
    """Redacta rutas y URLs con datos, conservando solo el host de la URL."""
    texto = _URL.sub(_url_sin_datos, texto)
    return _RUTA_ABSOLUTA.sub(RUTA, texto)


def ruta_para_log(_valor: Any) -> str:
    return RUTA


def nombre_para_log(_valor: Any) -> str:
    return ARCHIVO


def url_para_log(_valor: Any) -> str:
    return URL


def error_para_log(exc: BaseException) -> str:
    return type(exc).__name__


def _tipo_de_excepcion(exc_info: Any) -> str:
    try:
        if isinstance(exc_info, tuple) and len(exc_info) >= 2:
            return type(exc_info[1]).__name__
        if isinstance(exc_info, BaseException):
            return type(exc_info).__name__
    except Exception:  # noqa: BLE001
        return ERROR
    return ERROR


def _sanear_valor(clave: str, valor: Any) -> Any:
    if clave in _CLAVES_ARCHIVO:
        return ARCHIVO
    if clave in _CLAVES_RUTA:
        return RUTA
    if clave in _CLAVES_URL:
        return URL
    if isinstance(valor, dict):
        return {str(k): _sanear_valor(str(k), v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sanear_valor(clave, v) for v in valor]
    if isinstance(valor, str):
        return sanear_texto(valor)
    return valor


def sanear_evento(_logger: Any, _metodo: str, evento: dict[str, Any]) -> dict[str, Any]:
    """Procesador de structlog: sanea el evento antes de renderizarlo o guardarlo.

    Las trazas de excepción se sustituyen por el tipo de error: una traza puede
    contener rutas del archivo de la persona en el mensaje de la excepción. Se
    conserva el tipo y los identificadores del evento; el detalle de la traza no
    se publica.
    """
    limpio = dict(evento)
    exc = limpio.get("exc_info")
    if exc:
        limpio["exc_info"] = False
        limpio.setdefault("error_type", _tipo_de_excepcion(exc))
    for clave, valor in list(limpio.items()):
        limpio[str(clave)] = _sanear_valor(str(clave), valor)
    return limpio


class FiltroLogsSinRutas(logging.Filter):
    """Filtro para logs estándar (uvicorn.error): mensaje y tipo, sin traza con rutas."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Solo las trazas de excepción: los mensajes normales de uvicorn (p. ej.
        # el handshake de WebSocket) son parte del contrato de #361 y no llevan
        # la traza con rutas.
        if not record.exc_info:
            return True
        try:
            record.msg = sanear_texto(str(record.msg))
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: sanear_texto(v) if isinstance(v, str) else v
                                   for k, v in record.args.items()}
                else:
                    record.args = tuple(sanear_texto(v) if isinstance(v, str) else v
                                        for v in record.args)
            exc = record.exc_info
            if exc and isinstance(exc, tuple) and len(exc) >= 2:
                record.msg = f"{record.msg} [error: {type(exc[1]).__name__}]"
                record.exc_info = None
                record.exc_text = None
        except Exception:  # noqa: BLE001 — un filtro nunca tumba el log
            return True
        return True


__all__ = [
    "ARCHIVO", "ERROR", "RUTA", "URL", "error_para_log", "nombre_para_log",
    "FiltroLogsSinRutas", "ruta_para_log", "sanear_evento", "sanear_texto",
    "url_para_log",
]
