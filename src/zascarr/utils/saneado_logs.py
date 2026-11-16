"""SEC-LOG (#369): una única política de saneo para logs.

No toca la UI ni los mensajes de pantalla: solo lo que se escribe al registro. Sin I/O por
evento: las raíces sensibles se cachean y se refrescan al arrancar/cambiar ajustes.
"""
from __future__ import annotations

import logging
import re
import threading
import traceback
from pathlib import Path
from typing import Any

import structlog

_CLAVE_SECRETA = re.compile(
    r"(?i)(password|passwd|contrase(?:n|ñ)a|secret|token|api[_-]?key|authorization|cookie|bearer|session)")
_URL = re.compile(r"(?i)\b(https?|ftp)://(?:[^/@\s]+@)?([^/\s?#:]+)[^\s\"'<>]*")
_URL_SIN_ESQUEMA = re.compile(r"(?i)\b(?:www\.)[^\s\"'<>]+")
_CREDENCIAL = re.compile(
    r"(?i)((?:password|passwd|contrase(?:n|ñ)a|secret|token|api[_-]?key|authorization|cookie|session)"
    r"\s*[=:]\s*)[^\s,;\"']+")
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_EXT = r"(?:cbz|cbr|cb7|pdf|epub)"
_ABS_COMIC = re.compile(rf"(?i)(?<![\w])/(?:[^\s\"'<>/]+/)+[^\s\"'<>/]+\.({_EXT})\b")
_ARCHIVO_SIMPLE = re.compile(rf"(?i)\b[^\s\"'<>/]+\.({_EXT})\b")
_RUTA_ABS = re.compile(r"(?<!\w)/(?:[^\s\"'<>/]+/)*[^\s\"'<>/]*")
_MAX = 2000

_raices: tuple[str, ...] = ()
_lock = threading.Lock()


def refrescar_raices(raices: list[str | Path] | None = None) -> None:
    """Cachea las raíces sensibles. Nunca se llama desde el procesador."""
    global _raices
    valores: list[str] = []
    if raices is None:
        try:
            from zascarr.config import get_settings
            a = get_settings()
            for nombre in ("library_path", "downloads_path", "transmission_download_dir",
                           "amule_incoming_dir", "covers_cache_path", "export_path",
                           "library_roots"):
                valor = getattr(a, nombre, None)
                if valor:
                    valores.append(str(valor))
        except Exception:  # noqa: BLE001 — arranque sin settings
            valores = []
    else:
        valores = [str(x) for x in raices]
    normalizadas = set()
    for valor in valores:
        try:
            p = Path(valor).resolve(strict=False)
            normalizadas.add(str(p))
            normalizadas.add(str(Path(valor)))
        except (OSError, ValueError):
            continue
    with _lock:
        _raices = tuple(sorted(normalizadas, key=len, reverse=True))


def _redactar_url(texto: str) -> str:
    def sub(m: re.Match[str]) -> str:
        return f"{m.group(1)}://{m.group(2)}/[url]"
    return _URL.sub(sub, _URL_SIN_ESQUEMA.sub("[url]", texto))


def _redactar_credenciales(texto: str) -> str:
    texto = _CREDENCIAL.sub(r"\1[credencial]", texto)
    return _BEARER.sub(r"\1[credencial]", texto)


def sanear_texto(texto: str, *, raices: tuple[str, ...] | None = None) -> str:
    """Redacta ruta/archivo/URL/credencial de un texto, de forma idempotente."""
    if not isinstance(texto, str) or not texto:
        return texto
    if len(texto) > _MAX:
        texto = texto[:_MAX] + "…"
    try:
        resultado = _redactar_credenciales(texto)
        resultado = _redactar_url(resultado)
        for raiz in (raices if raices is not None else _raices):
            if raiz in resultado:
                resultado = re.sub(re.escape(raiz) + r"[^\s\"'<>]*", "[ruta]", resultado)
        resultado = _ABS_COMIC.sub("[archivo]", resultado)
        resultado = _ARCHIVO_SIMPLE.sub("[archivo]", resultado)
        return resultado
    except Exception:  # noqa: BLE001 — falla cerrado
        return "[no_saneado]"


def sanear_valor(valor: Any, *, clave: str = "", profundidad: int = 0) -> Any:
    if profundidad > 8:
        return "[no_saneado]"
    try:
        if _CLAVE_SECRETA.search(clave):
            return "[credencial]"
        if isinstance(valor, str):
            return sanear_texto(valor)
        if isinstance(valor, dict):
            return {sanear_texto(str(k)): sanear_valor(v, clave=str(k), profundidad=profundidad + 1)
                    for k, v in valor.items()}
        if isinstance(valor, (list, tuple)):
            return [sanear_valor(v, clave=clave, profundidad=profundidad + 1) for v in valor]
        return valor
    except Exception:  # noqa: BLE001
        return "[no_saneado]"


def sanear_evento(_logger: Any, _metodo: str, evento: dict[str, Any]) -> dict[str, Any]:
    """Procesador structlog: copia y sanea evento, campos y traceback."""
    try:
        salida: dict[str, Any] = {}
        for clave, valor in evento.items():
            k = sanear_texto(str(clave))
            if k in {"event", "exception", "exc_text"} and isinstance(valor, str):
                salida[k] = sanear_texto(valor)
            else:
                salida[k] = sanear_valor(valor, clave=str(clave))
        return salida
    except Exception:  # noqa: BLE001 — nunca emitir crudo
        return {"event": "log.saneo_fallido"}


class FiltroSaneado(logging.Filter):
    """Filtro stdlib/uvicorn: sanea msg, args y exc_text sin silenciar el evento."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        try:
            if isinstance(record.msg, str):
                record.msg = sanear_texto(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        str(k): sanear_valor(v, clave=str(k))
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(sanear_valor(v) for v in record.args)
            if record.exc_info and not record.exc_text:
                record.exc_text = sanear_texto(
                    "".join(traceback.format_exception(*record.exc_info)))
            elif record.exc_text:
                record.exc_text = sanear_texto(record.exc_text)
            return True
        except Exception:  # noqa: BLE001
            record.msg = "(registro omitido: saneo fallido)"
            record.args = ()
            record.exc_text = "(traza omitida: saneo fallido)"
            return True


# Alias explícito del nombre del encargo.
SaneadorDeRegistro = FiltroSaneado


def _marcado(procesador: Any) -> bool:
    return getattr(procesador, "__name__", "") in {"sanear_evento", "SaneadorStructlog"}


def instalar_saneo_structlog() -> None:
    """Inserta el saneador antes del renderer y del capturador; idempotente."""
    config = structlog.get_config()
    procesadores = list(config.get("processors") or [])
    if any(_marcado(p) for p in procesadores):
        return
    tiene_exc = any(getattr(p, "__name__", "") in {"format_exc_info", "ExceptionRenderer"}
                    for p in procesadores)
    if not tiene_exc:
        procesadores.insert(max(0, len(procesadores) - 1), structlog.processors.format_exc_info)
    indice = len(procesadores) - 1
    for i, p in enumerate(procesadores):
        if getattr(p, "__name__", "") == "capturar":
            indice = i
            break
    procesadores.insert(indice, sanear_evento)
    structlog.configure(**{**config, "processors": procesadores})


def instalar_filtro_registros() -> None:
    """Añade el filtro a uvicorn.error y handlers raíz existentes; idempotente."""
    logger = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, FiltroSaneado) for f in logger.filters):
        logger.addFilter(FiltroSaneado())
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, FiltroSaneado) for f in handler.filters):
            try:
                handler.addFilter(FiltroSaneado())
            except Exception:  # noqa: BLE001 — un handler exótico no tumba el arranque
                continue


def instalar_saneo_logs() -> None:
    refrescar_raices()
    instalar_saneo_structlog()
    instalar_filtro_registros()
