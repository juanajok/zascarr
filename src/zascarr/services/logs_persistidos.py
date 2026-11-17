"""Consulta de los logs JSONL persistidos y rotados por la propia app.

No hay base de datos ni índice: los ficheros `zascarr-AAAA-MM-DD.jsonl` los
escribe `utils/registro_archivo.py`. Se leen bajo demanda y se filtran por
fecha, hora y evento; el resultado está ya saneado por #369.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from zascarr.config import get_settings

_NOMBRE = re.compile(r"^zascarr-(\d{4}-\d{2}-\d{2})(?:\.(\d+))?\.jsonl$")
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HORA = re.compile(r"^\d{2}(?::\d{2})?$")
_MAX = 1000


def directorio(settings=None) -> Path:
    return Path(getattr(settings or get_settings(), "log_dir", "/config/logs"))


def _archivos(directorio_logs: Path, fecha: str | None = None) -> list[Path]:
    if not directorio_logs.is_dir():
        return []
    salida = []
    for entrada in directorio_logs.iterdir():
        if not entrada.is_file():
            continue
        m = _NOMBRE.match(entrada.name)
        if m is None:
            continue
        if fecha is not None and m.group(1) != fecha:
            continue
        salida.append(entrada)
    return sorted(salida, key=lambda p: p.name, reverse=True)


def dias_disponibles(settings=None) -> list[dict]:
    """Días con fichero y tamaño total; para el selector del visor."""
    por_dia: dict[str, int] = {}
    for archivo in _archivos(directorio(settings)):
        m = _NOMBRE.match(archivo.name)
        if m is None:
            continue
        try:
            por_dia[m.group(1)] = por_dia.get(m.group(1), 0) + archivo.stat().st_size
        except OSError:
            continue
    return [{"fecha": k, "bytes": v} for k, v in sorted(por_dia.items(), reverse=True)]


def _evento(linea: str) -> dict | None:
    try:
        dato = json.loads(linea)
    except (ValueError, TypeError):
        return None
    return dato if isinstance(dato, dict) else None


def _hora(evento: dict) -> str:
    texto = str(evento.get("timestamp") or "")
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00")).strftime("%H:%M")
    except (ValueError, TypeError):
        return ""


def leer_eventos(settings=None, *, fecha: str = "", hora: str = "",
                 evento: str = "", limite: int = 300) -> list[dict]:
    """Eventos más recientes que cumplen los filtros; nunca devuelve más de `_MAX`."""
    if fecha and not _FECHA.match(fecha):
        return []
    if hora and not _HORA.match(hora):
        return []
    limite = max(1, min(int(limite), _MAX))
    encontrados: list[dict] = []
    for archivo in _archivos(directorio(settings), fecha or None):
        try:
            with archivo.open("r", encoding="utf-8", errors="replace") as fh:
                for linea in fh:
                    dato = _evento(linea)
                    if dato is None:
                        continue
                    if hora:
                        h = _hora(dato)
                        if not (h == hora or (len(hora) == 2 and h.startswith(hora + ":"))):
                            continue
                    if evento and str(dato.get("event", "")) != evento:
                        continue
                    encontrados.append(dato)
                    if len(encontrados) >= limite:
                        break
        except OSError:
            continue
        if len(encontrados) >= limite:
            break
    # Los ficheros se recorren de más nuevo a más viejo; dentro de un fichero se
    # conserva el orden de escritura. El visor muestra lo más reciente primero.
    return encontrados[:limite]


def eventos_disponibles(settings=None, *, fecha: str = "") -> list[str]:
    nombres = {str(e.get("event")) for e in leer_eventos(settings, fecha=fecha, limite=_MAX)
               if e.get("event")}
    return sorted(nombres)


def texto_jsonl(eventos: list[dict]) -> str:
    return "\n".join(json.dumps(e, ensure_ascii=False, sort_keys=True) for e in eventos) + (
        "\n" if eventos else "")
