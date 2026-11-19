"""SEC-LOG (#369): una única política de saneo para logs.

No toca la UI ni los mensajes de pantalla: solo lo que se escribe al registro. Sin I/O por
evento: las raíces sensibles se cachean y se refrescan al arrancar/cambiar ajustes.
"""
from __future__ import annotations

import contextlib
import logging
import re
import threading
import traceback
from pathlib import Path
from typing import Any

import structlog

_CLAVE_SECRETA = re.compile(
    r"(?i)(password|passwd|contrase(?:n|ñ)a|secret|token|api[_-]?key|authorization|cookie|bearer|session)")
_FILE_URL = re.compile(r"(?i)file://[^\s\"'<>]+")
_URL = re.compile(r"(?i)\b([A-Za-z][A-Za-z0-9+.-]*)://(?:[^/@\s]+@)?([^/\s?#:]+)[^\s\"'<>]*")
_URL_SIN_ESQUEMA = re.compile(r"(?i)\b(?:www\.)[^\s\"'<>]+")
_CREDENCIAL_CITA = re.compile(
    r"(?i)([\"\']?(?:password|passwd|secret|token|api[_-]?key|authorization|cookie)[\"\']?"
    r"\s*[=:]\s*)([\"\'])[^\"\']*\2")
_CREDENCIAL = re.compile(
    r"(?i)((?:password|passwd|contrase(?:n|ñ)a|secret|token|api[_-]?key|authorization|cookie|session)"
    r"\s*[=:]\s*)[^\s,;\"']+")
_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+")
_EXT = r"(?:cbz|cbr|cb7|pdf|epub)"
_ABS_COMIC = re.compile(rf"(?i)(?<![\w])/(?:[^\s\"'<>/]+/)+[^\s\"'<>/]+\.({_EXT})\b")
_RUTA_RELATIVA = re.compile(rf"(?i)(?<![\w])[^\s\"'<>/]+(?:/[^\s\"'<>/]+)+\.({_EXT})\b")
_ARCHIVO_SIMPLE = re.compile(rf"(?i)\b[^\s\"'<>/]+\.({_EXT})\b")
_RUTA_ABS = re.compile(
    r"(?<![:/\w])/(?:[^\n\"'<>]*?)(?=:\s|$|[\"';,\)\]]|\s+\(|\s+-\s)",
    re.MULTILINE)
#: Placeholders de printf en un `LogRecord.msg` con `args`: el saneo de la
#: plantilla no puede cambiar su número, o `record.getMessage()` revienta.
_FORMATO = re.compile(r"%(?:\([^)]+\))?[#0\- +]?\d*(?:\.\d+)?[hlL]?[diouxXeEfFgGcrsa%]")
_MAX = 2000
#: Prefiltro barato: si no hay nada con pinta sensible, no se recorren los regex.
_SOSPECHOSO = re.compile(
    r"[/:@=.#'\"\\]|(?i:bearer|password|passwd|contrase|secret|token|api[_-]?key|authorization|cookie|session)")

_raices: tuple[str, ...] = ()
_lock = threading.Lock()


def refrescar_raices(raices: list[str | Path] | None = None) -> None:
    """Une configuración, BD y raíces explícitas; nunca reemplaza las conocidas."""
    global _raices
    valores: list[str] = []
    with contextlib.suppress(Exception):  # arranque sin settings
        from zascarr.config import get_settings
        a = get_settings()
        for nombre in ("library_path", "downloads_path", "transmission_download_dir",
                       "amule_incoming_dir", "covers_cache_path", "export_path",
                       "library_roots"):
            valor = getattr(a, nombre, None)
            if valor:
                for parte in str(valor).replace(";", ",").split(","):
                    if parte.strip():
                        valores.append(parte.strip())
    if raices:
        for x in raices:
            valores.extend(parte.strip() for parte in str(x).replace(";", ",").split(",")
                           if parte.strip())
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
    texto = _CREDENCIAL_CITA.sub(r'\1\2[credencial]\2', texto)
    texto = _CREDENCIAL.sub(r"\1[credencial]", texto)
    return _BEARER.sub(r"\1[credencial]", texto)


def sanear_texto(texto: str, *, raices: tuple[str, ...] | None = None) -> str:
    """Redacta ruta/archivo/URL/credencial de un texto, de forma idempotente."""
    if not isinstance(texto, str) or not texto:
        return texto
    if len(texto) > _MAX:
        texto = texto[:_MAX] + "…"
    if not _SOSPECHOSO.search(texto):
        return texto
    try:
        resultado = _redactar_credenciales(texto)
        resultado = _FILE_URL.sub("file:///[ruta]", resultado)
        codigo: list[str] = []
        for patron in (r"/app/src/zascarr/[^\s\"'<>]*",
                       re.escape(str(Path(__file__).resolve().parents[1])) + r"/[^\s\"'<>]*"):
            def guardar_codigo(m: re.Match[str]) -> str:
                codigo.append(m.group(0))
                return f"\x00CODIGO{len(codigo)-1}\x00"
            resultado = re.sub(patron, guardar_codigo, resultado)
        urls: list[str] = []
        def guardar(m: re.Match[str]) -> str:
            urls.append(_redactar_url(m.group(0)))
            return f"\x00URL{len(urls)-1}\x00"
        resultado = _URL.sub(guardar, resultado)
        for raiz in (raices if raices is not None else _raices):
            if raiz in resultado:
                resultado = re.sub(re.escape(raiz) + r"[^\n\"'<>]*", "[ruta]", resultado)
        resultado = _ABS_COMIC.sub("[archivo]", resultado)
        resultado = _RUTA_ABS.sub("[ruta]", resultado)
        resultado = _RUTA_RELATIVA.sub("[ruta]", resultado)
        resultado = _ARCHIVO_SIMPLE.sub("[archivo]", resultado)
        for i, url in enumerate(urls):
            resultado = resultado.replace(f"\x00URL{i}\x00", url)
        for i, trozo in enumerate(codigo):
            resultado = resultado.replace(f"\x00CODIGO{i}\x00", trozo)
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
        if isinstance(valor, Path):
            return sanear_texto(str(valor))
        if isinstance(valor, BaseException):
            return sanear_texto(f"{type(valor).__name__}: {valor}")
        if isinstance(valor, bytes):
            return sanear_texto(valor.decode("utf-8", "replace"))
        if isinstance(valor, (int, float, bool)) or valor is None:
            return valor
        try:
            return sanear_texto(repr(valor))
        except Exception:  # noqa: BLE001
            return "[no_saneado]"
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


def _sanear_mensaje(record: logging.LogRecord) -> None:
    """Sanea `record.msg` sin tocar sus placeholders de printf.

    Con `args`, el mensaje es una plantilla: se sanean solo los tramos
    literales y se conservan `%s`/`%d` (si se sustituyeran por `[ruta]`, el
    `record.getMessage()` de uvicorn fallaría por número de argumentos).
    """
    if not isinstance(record.msg, str):
        record.msg = sanear_valor(record.msg)
        return
    if not record.args:
        record.msg = sanear_texto(record.msg)
        return
    def _tramo(texto: str) -> str:
        # Un tramo de solo puntuación («/», «://») no es una ruta: saneado
        # lo convertiría en «[ruta]» y rompería el formato de uvicorn.
        if not texto.strip("/:.- "):
            return texto
        return sanear_texto(texto)

    partes: list[str] = []
    ultimo = 0
    for m in _FORMATO.finditer(record.msg):
        partes.append(_tramo(record.msg[ultimo:m.start()]))
        partes.append(m.group(0))
        ultimo = m.end()
    partes.append(_tramo(record.msg[ultimo:]))
    record.msg = "".join(partes)


class FiltroSaneado(logging.Filter):
    """Filtro stdlib/uvicorn: sanea msg, args y exc_text sin silenciar el evento."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        if record.name == "uvicorn.access":
            return True  # #361 ya quita la query; #369 no toca ese registro
        try:
            _sanear_mensaje(record)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        str(k): sanear_valor(v, clave=str(k))
                        for k, v in record.args.items()
                    }
                else:
                    record.args = tuple(sanear_valor(v) for v in record.args)
            for nombre, valor in list(record.__dict__.items()):
                if nombre in {"msg", "args", "exc_info", "exc_text", "stack_info",
                              "name", "levelname", "levelno", "pathname", "filename",
                              "module", "lineno", "funcName", "created", "msecs",
                              "relativeCreated", "thread", "threadName", "process",
                              "processName", "taskName"}:
                    continue
                record.__dict__[nombre] = sanear_valor(valor, clave=nombre)
            if record.stack_info:
                record.stack_info = sanear_texto(record.stack_info)
            if record.exc_info and not record.exc_text:
                record.exc_text = sanear_texto(
                    "".join(traceback.format_exception(*record.exc_info)))
            elif record.exc_text:
                record.exc_text = sanear_texto(record.exc_text)
            record.exc_info = None  # un formatter de %(exc_info)s no ve la tupla cruda
            return True
        except Exception:  # noqa: BLE001
            record.msg = "(registro omitido: saneo fallido)"
            record.args = ()
            record.exc_text = "(traza omitida: saneo fallido)"
            record.exc_info = None
            return True


# Alias explícito del nombre del encargo.
SaneadorDeRegistro = FiltroSaneado


def _marcado(procesador: Any) -> bool:
    return getattr(procesador, "__name__", "") in {"sanear_evento", "SaneadorStructlog"}


def instalar_saneo_structlog() -> None:
    """Inserta el saneador antes del renderer y del capturador; idempotente."""
    config = structlog.get_config()
    procesadores = list(config.get("processors") or [])
    if not procesadores:
        procesadores = [structlog.processors.format_exc_info,
                        structlog.dev.ConsoleRenderer()]
    if any(_marcado(p) for p in procesadores):
        return
    if not any(getattr(p, "__name__", "") in {"format_exc_info", "ExceptionRenderer"}
               for p in procesadores):
        procesadores.insert(0, structlog.processors.format_exc_info)
    captura = next((i for i, p in enumerate(procesadores)
                    if getattr(p, "__name__", "") == "capturar"), None)
    if captura is not None:
        procesadores.insert(captura, sanear_evento)
    else:
        procesadores.insert(max(0, len(procesadores) - 1), sanear_evento)
    structlog.configure(**{**config, "processors": procesadores})


_FABRICA_INSTALADA = False


def _sanear_record_en_origen(record: logging.LogRecord) -> None:
    """Sanea el LogRecord en el momento de crearlo, antes de cualquier handler."""
    if record.name == "uvicorn.access":
        return  # #361: su formateador necesita args intactos
    if getattr(record, "_sec_log_saneado", False):
        return
    try:
        _sanear_mensaje(record)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {str(k): sanear_valor(v, clave=str(k))
                               for k, v in record.args.items()}
            else:
                record.args = tuple(sanear_valor(v) for v in record.args)
        for nombre, valor in list(record.__dict__.items()):
            if nombre.startswith("_") or nombre in {"msg", "args", "exc_info", "exc_text",
                                                     "stack_info", "name", "levelname",
                                                     "levelno", "pathname", "filename",
                                                     "module", "lineno", "funcName",
                                                     "created", "msecs", "relativeCreated",
                                                     "thread", "threadName", "process",
                                                     "processName", "taskName"}:
                continue
            record.__dict__[nombre] = sanear_valor(valor, clave=nombre)
        if record.stack_info:
            record.stack_info = sanear_texto(record.stack_info)
        if record.exc_info and not record.exc_text:
            record.exc_text = sanear_texto(
                "".join(traceback.format_exception(*record.exc_info)))
        elif record.exc_text:
            record.exc_text = sanear_texto(record.exc_text)
        # Un formatter que use %(exc_info)s no debe poder imprimir la tupla cruda.
        record.exc_info = None
        record._sec_log_saneado = True
    except Exception:  # noqa: BLE001 — nunca emitir crudo
        record.msg = "(registro omitido: saneo fallido)"
        record.args = ()
        record.exc_info = None


def instalar_fabrica_de_registros() -> None:
    """Sanea en ORIGEN: cubre handlers/loggers creados después sin reinstalar."""
    global _FABRICA_INSTALADA
    if _FABRICA_INSTALADA:
        return
    anterior = logging.getLogRecordFactory()

    def fabrica(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = anterior(*args, **kwargs)
        _sanear_record_en_origen(record)
        return record

    logging.setLogRecordFactory(fabrica)
    _FABRICA_INSTALADA = True


def instalar_filtro_registros() -> None:
    """Añade el filtro y la fábrica de saneo; idempotente."""
    instalar_fabrica_de_registros()
    logger = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, FiltroSaneado) for f in logger.filters):
        logger.addFilter(FiltroSaneado())
    raiz = logging.getLogger()
    if not any(isinstance(f, FiltroSaneado) for f in raiz.filters):
        raiz.addFilter(FiltroSaneado())
    uvicorn_handlers = {id(h) for h in logging.getLogger("uvicorn").handlers}
    for handler in logging.getLogger().handlers:
        if id(handler) in uvicorn_handlers:
            continue
        if not any(isinstance(f, FiltroSaneado) for f in handler.filters):
            with contextlib.suppress(Exception):  # un handler exótico no tumba el arranque
                handler.addFilter(FiltroSaneado())


def instalar_saneo_logs() -> None:
    refrescar_raices()
    instalar_saneo_structlog()
    instalar_filtro_registros()


async def refrescar_raices_db(fabrica) -> None:
    """Refresca el cache con las raíces de la BD; se llama al arrancar/cambiar raíces."""
    try:
        from sqlalchemy import select

        from zascarr.models import LibraryRoot
        async with fabrica() as s:
            rutas = list((await s.execute(select(LibraryRoot.path))).scalars())
        refrescar_raices(rutas)
    except Exception:  # noqa: BLE001 — un fallo al refrescar no tumba el arranque
        return
