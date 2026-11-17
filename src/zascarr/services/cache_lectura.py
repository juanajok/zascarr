"""Caché de extracción de CBR/RAR para el lector (BL-LEC4, #827).

Una extracción por archivo, en un temporal dentro de la propia caché, y publicación atómica
con `os.replace`. Nunca se escribe en la biblioteca. La cuota y el turno de `unar` se
comparten con el resto del proceso a través de `utils.lector_rar`.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from zascarr.config import Settings, get_settings
from zascarr.models import File, MotivoRar
from zascarr.utils.lector_rar import ErrorRar, extraer_completo

logger = structlog.get_logger()

ACTIVO_S = 300.0
_CT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".avif": "image/avif",
}
_MOTIVO = {
    MotivoRar.CIFRADO: "El archivo está protegido con contraseña; no se puede preparar.",
    MotivoRar.MULTIVOLUMEN: (
        "El archivo necesita las demás partes del volumen; no se puede preparar."),
    MotivoRar.ILEGIBLE: "El archivo está dañado o no se puede leer.",
    MotivoRar.SIN_IMAGENES: "El archivo no tiene páginas de imagen.",
    MotivoRar.DEMASIADO_GRANDE: "Este tebeo es demasiado grande para prepararlo para leer.",
    MotivoRar.TIEMPO: "El archivo tarda demasiado en prepararse; vuelve a intentarlo.",
    MotivoRar.HERRAMIENTA_AUSENTE: "El lector de CBR no está disponible en este equipo.",
    MotivoRar.OCUPADO: "El lector está ocupado preparando otro tebeo; vuelve a intentarlo.",
    MotivoRar.PAQUETE: "El archivo no es un tebeo suelto; no se puede preparar.",
    MotivoRar.INESPERADO: "No se ha podido preparar el tebeo.",
}


class CacheError(Exception):
    """Error de preparación; el texto ya es apto para el coleccionista."""


@dataclass
class Estado:
    estado: str
    motivo: str = ""


@dataclass
class CacheLectura:
    base: Path
    cuota: int
    timeout: float
    max_bytes: int
    max_ficheros: int
    _tareas: dict[str, asyncio.Task] = field(default_factory=dict)
    _errores: dict[str, str] = field(default_factory=dict)
    _cuota_lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def desde_ajustes(cls, settings: Settings | None = None) -> CacheLectura:
        s = settings or get_settings()
        base = s.lector_cache_path.resolve()
        biblioteca = s.library_path.resolve()
        if base == biblioteca or base.is_relative_to(biblioteca):
            raise ValueError("La caché del lector no puede estar dentro de la biblioteca")
        return cls(s.lector_cache_path, s.lector_cache_bytes, s.lector_extraccion_timeout_s,
                   s.lector_extraccion_max_bytes, s.lector_extraccion_max_ficheros)

    def clave(self, file: File) -> str:
        base = file.sha256_hash or str(file.file_mtime_ns or file.id)
        return f"{file.id}-{base[:12]}"

    def ruta(self, file: File) -> Path:
        return self.base / self.clave(file)

    def _paginas(self, file: File) -> list[Path]:
        ruta = self.ruta(file)
        if not ruta.is_dir():
            return []
        return sorted((p for p in ruta.iterdir()
                       if p.is_file() and not p.is_symlink()
                       and p.suffix.lower() in _CT), key=lambda p: p.name)

    def estado(self, file: File) -> Estado:
        clave = self.clave(file)
        if clave in self._errores:
            return Estado("error", self._errores[clave])
        if self._paginas(file):
            return Estado("listo")
        return Estado("preparando")

    async def preparar(self, file: File) -> Estado:
        clave = self.clave(file)
        actual = self.estado(file)
        if actual.estado != "preparando" or clave in self._errores:
            return actual
        if clave not in self._tareas or self._tareas[clave].done():
            tarea = asyncio.create_task(self._extraer(file), name=f"lec4-{clave}")
            self._tareas[clave] = tarea
            tarea.add_done_callback(lambda _t, c=clave: self._tareas.pop(c, None))
        return Estado("preparando")

    async def _extraer(self, file: File) -> None:
        clave = self.clave(file)
        try:
            await asyncio.to_thread(self._extraer_sync, file)
        except CacheError as exc:
            self._errores[clave] = str(exc)
        except ErrorRar as exc:
            if exc.motivo not in (MotivoRar.OCUPADO, MotivoRar.TIEMPO,
                                  MotivoRar.HERRAMIENTA_AUSENTE):
                self._errores[clave] = _MOTIVO.get(exc.motivo, _MOTIVO[MotivoRar.INESPERADO])
        except Exception as exc:  # noqa: BLE001 — una extracción no puede tumbar el proceso
            logger.warning("lector.cache_error", tipo=type(exc).__name__)
            self._errores[clave] = _MOTIVO[MotivoRar.INESPERADO]

    def _tamano(self, ruta: Path) -> int:
        total = 0
        for raiz, _dirs, ficheros in os.walk(ruta):
            for nombre in ficheros:
                try:
                    total += os.lstat(os.path.join(raiz, nombre)).st_size
                except OSError:
                    continue
        return total

    def _hacer_sitio(self, necesario: int, clave_actual: str) -> None:
        with self._cuota_lock:
            self._hacer_sitio_bloqueado(necesario, clave_actual)

    def _hacer_sitio_bloqueado(self, necesario: int, clave_actual: str) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        actuales = []
        total = 0
        for hijo in self.base.iterdir():
            if not hijo.is_dir():
                continue
            tam = self._tamano(hijo)
            total += tam
            actuales.append((hijo, tam))
        if total + necesario <= self.cuota:
            return
        ahora = time.time()
        for hijo, tam in sorted(actuales,
                                key=lambda x: self._mtime(x[0])):
            if (hijo.name == clave_actual or hijo.name in self._tareas
                    or hijo.name.startswith(".tmp-")):
                continue
            if ahora - self._mtime(hijo) < ACTIVO_S:
                continue
            shutil.rmtree(hijo, ignore_errors=True)
            total -= tam
            if total + necesario <= self.cuota:
                return
        raise CacheError("No hay espacio en la caché de lectura para preparar este tebeo.")

    @staticmethod
    def _mtime(ruta: Path) -> float:
        try:
            return ruta.stat().st_mtime
        except OSError:
            return 0.0

    def _extraer_sync(self, file: File) -> None:
        clave = self.clave(file)
        ruta = Path(file.file_path)
        if ruta.is_symlink() or not ruta.is_file():
            raise CacheError("El archivo no está disponible en el disco.")
        declarado = file.file_size_bytes or 0
        if declarado > self.cuota:
            raise CacheError("Este tebeo es demasiado grande para prepararlo para leer.")
        self._hacer_sitio(max(declarado, 1), clave)
        self.base.mkdir(parents=True, exist_ok=True)
        libre = max(0, self.cuota - self._tamano(self.base))
        if libre <= 0:
            raise CacheError("No hay espacio en la caché de lectura para preparar este tebeo.")
        trabajo = Path(tempfile.mkdtemp(prefix=f".tmp-{clave}-", dir=self.base))
        try:
            salida = trabajo / "salida"
            imagenes = extraer_completo(
                ruta, salida, temporal=trabajo,
                timeout=self.timeout, max_bytes=min(self.max_bytes, libre),
                max_ficheros=self.max_ficheros)
            total_extraido = sum(i.tamano for i in imagenes)
            if total_extraido > self.cuota:
                raise CacheError("Este tebeo es demasiado grande para prepararlo para leer.")
            limpio = trabajo / "limpio"
            limpio.mkdir(mode=0o700)
            for numero, imagen in enumerate(imagenes, start=1):
                extension = imagen.ruta.suffix.lower()
                destino = limpio / f"{numero:05d}{extension}"
                os.replace(imagen.ruta, destino)
            final = self.base / clave
            if final.exists():
                shutil.rmtree(final, ignore_errors=True)
            os.replace(limpio, final)
            os.utime(final, None)
        finally:
            shutil.rmtree(trabajo, ignore_errors=True)

    def leer_pagina(self, file: File, n: int) -> tuple[bytes, str]:
        paginas = self._paginas(file)
        if n < 1 or n > len(paginas):
            raise CacheError("Esa página no existe.")
        ruta = paginas[n - 1]
        try:
            datos = ruta.read_bytes()
            os.utime(self.ruta(file), None)
        except OSError as exc:
            raise CacheError("No se pudo leer la página preparada.") from exc
        return datos, _CT.get(ruta.suffix.lower(), "application/octet-stream")


def barrer_temporales(base: Path) -> int:
    """Borra temporales de extracciones que murieron (BL-LEC4): nunca toca una caché publicada."""
    if not base.is_dir():
        return 0
    borrados = 0
    for hijo in base.iterdir():
        if hijo.is_dir() and hijo.name.startswith(".tmp-"):
            shutil.rmtree(hijo, ignore_errors=True)
            borrados += 1
    return borrados
