"""Sumidero JSONL persistente y rotado para los logs de ZascArr.

stdout/Docker sigue siendo la salida principal; este fichero existe para que el
coleccionista pueda consultar **logs anteriores** desde la UI sin montar el
socket de Docker. Recibe eventos ya saneados (#369), escribe una línea JSON por
evento y rota:

- un fichero por día UTC (`zascarr-AAAA-MM-DD.jsonl`);
- al superar `LOG_MAX_BYTES`, se desplaza a `.1`, `.2`… y se conserva
  `LOG_BACKUPS` por día;
- se borran los días anteriores a `LOG_RETENTION_DAYS`.

Las escrituras son O_APPEND + una sola escritura por línea; el fichero se crea
0600 y el directorio 0700. Un fallo de disco nunca tumba la petición: el
sumidero falla cerrado y deja el evento solo en stdout.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

_NOMBRE = re.compile(r"^zascarr-(\d{4}-\d{2}-\d{2})(?:\.(\d+))?\.jsonl$")
_lock = threading.Lock()
_writer: EscritorJsonl | None = None


class EscritorJsonl:
    def __init__(self, directorio: Path, *, max_bytes: int = 5 * 1024 * 1024,
                 backups: int = 3, retencion_dias: int = 30):
        self.directorio = Path(directorio)
        self.max_bytes = max(1024, int(max_bytes))
        self.backups = max(0, int(backups))
        self.retencion_dias = max(1, int(retencion_dias))
        self._dia: str | None = None
        self.directorio.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.directorio, 0o700)

    @staticmethod
    def _dia_de(evento: dict) -> str:
        texto = str(evento.get("timestamp") or "")
        try:
            return (
                datetime.fromisoformat(texto.replace("Z", "+00:00"))
                .astimezone(UTC).date().isoformat()
            )
        except (TypeError, ValueError, OSError):
            return datetime.now(UTC).date().isoformat()

    def _ruta(self, dia: str) -> Path:
        return self.directorio / f"zascarr-{dia}.jsonl"

    def _rotar(self, ruta: Path) -> None:
        try:
            for n in range(self.backups, 0, -1):
                origen = ruta.with_name(f"{ruta.stem}.{n}{ruta.suffix}")
                if origen.exists():
                    if n == self.backups:
                        origen.unlink(missing_ok=True)
                    else:
                        origen.replace(ruta.with_name(f"{ruta.stem}.{n + 1}{ruta.suffix}"))
            if ruta.exists():
                ruta.replace(ruta.with_name(f"{ruta.stem}.1{ruta.suffix}"))
        except OSError:
            return

    def _limpiar(self) -> None:
        limite = datetime.now(UTC) - timedelta(days=self.retencion_dias)
        try:
            for entrada in self.directorio.glob("zascarr-*.jsonl"):
                m = _NOMBRE.match(entrada.name)
                if not m:
                    continue
                try:
                    fecha = datetime.fromisoformat(m.group(1)).date()
                except ValueError:
                    continue
                if fecha < limite.date():
                    entrada.unlink(missing_ok=True)
        except OSError:
            return

    def escribir(self, evento: dict) -> None:
        try:
            linea = (json.dumps(evento, ensure_ascii=False, sort_keys=True,
                                default=str) + "\n").encode("utf-8")
        except (TypeError, ValueError):
            return
        dia = self._dia_de(evento)
        ruta = self._ruta(dia)
        with _lock:
            if self._dia is None or dia != self._dia:
                self._dia = dia
                self._limpiar()
            try:
                tam = ruta.stat().st_size if ruta.exists() else 0
            except OSError:
                tam = 0
            if tam and tam + len(linea) > self.max_bytes:
                self._rotar(ruta)
            try:
                fd = os.open(str(ruta), os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, linea)
                finally:
                    os.close(fd)
            except OSError:
                # El sumidero no puede tumbar el logging de la app.
                return


def escribir_evento(_logger=None, _metodo=None, evento=None):
    """Procesador structlog: escribe el evento ya saneado al fichero."""
    if isinstance(evento, dict) and _writer is not None:
        with contextlib.suppress(Exception):  # nunca romper una petición por el sumidero
            _writer.escribir(evento)
    return evento


def instalar_archivo_logs(settings=None) -> bool:
    """Instala el sumidero si el directorio se puede escribir. Idempotente."""
    global _writer
    from zascarr.config import get_settings

    ajustes = settings or get_settings()
    try:
        _writer = EscritorJsonl(
            Path(getattr(ajustes, "log_dir", "/config/logs")),
            max_bytes=getattr(ajustes, "log_max_bytes", 5 * 1024 * 1024),
            backups=getattr(ajustes, "log_backups", 3),
            retencion_dias=getattr(ajustes, "log_retention_days", 30),
        )
    except OSError:
        _writer = None
        structlog.get_logger().warning("logs.fichero_no_escribible")
        return False
    config = structlog.get_config()
    procesadores = list(config.get("processors") or [])
    if not any(getattr(p, "__name__", "") == "escribir_evento" for p in procesadores):
        # Justo después del saneador y antes del capturador/renderer.
        idx = next((i + 1 for i, p in enumerate(procesadores)
                    if getattr(p, "__name__", "") == "sanear_evento"), None)
        if idx is None:
            idx = max(0, len(procesadores) - 1)
        procesadores.insert(idx, escribir_evento)
        structlog.configure(**{**config, "processors": procesadores})
    return True
