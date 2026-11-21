"""Escritor aislado de estado de actualización; no ejecuta ni autoriza nada.

Escribe un JSON canónico en un temporal exclusivo del mismo directorio,
sincroniza el archivo, renombra y sincroniza el directorio. Ante cualquier
error devuelve INCIERTO: no se puede deducir si el nombre antiguo o el nuevo
sobrevivirá a un corte, y el llamador no debe tratarlo como éxito. Un fsync
correcto tampoco demuestra que el hardware o el filesystem respeten flush.
No comprueba propiedad del directorio, no adquiere cerrojos y no se conecta a
la UI ni al auxiliar.
"""
from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path

MAX_BYTES = 4096


class ResultadoEscritura(StrEnum):
    OK = "ok"
    INCIERTO = "incierto"
    INVALIDO = "invalido"


def _reemplazar(origen: str, destino: str, dir_fd: int) -> None:
    os.replace(origen, destino, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)


def escribir_estado(
    ruta: str | Path,
    datos: object,
    *,
    fsync: Callable[[int], None] = os.fsync,
    replace: Callable[[str, str, int], None] = _reemplazar,
) -> ResultadoEscritura:
    """Intenta publicar una instantánea; solo OK si todas las fases terminan."""
    try:
        destino = Path(ruta)
        contenido = _serializar(datos)
        directorio = destino.parent
        fd_dir = os.open(directorio, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except (OSError, TypeError, ValueError):
        return ResultadoEscritura.INVALIDO

    temporal = None
    fd = None
    try:
        try:
            info = os.fstat(fd_dir)
            if not stat.S_ISDIR(info.st_mode):
                return ResultadoEscritura.INVALIDO
            temporal = f".{destino.name}.tmp-{secrets.token_hex(8)}"
            fd = os.open(
                temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=fd_dir
            )
            _escribir_todo(fd, contenido)
            fsync(fd)
        except (OSError, TypeError, ValueError):
            return ResultadoEscritura.INCIERTO
        finally:
            if fd is not None:
                os.close(fd)
                fd = None
        try:
            replace(temporal, destino.name, fd_dir)
            temporal = None
            fsync(fd_dir)
        except (OSError, TypeError, ValueError):
            return ResultadoEscritura.INCIERTO
        return ResultadoEscritura.OK
    finally:
        if temporal is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporal, dir_fd=fd_dir)
        os.close(fd_dir)


def _serializar(datos: object) -> bytes:
    if not isinstance(datos, dict):
        raise ValueError
    texto = json.dumps(
        datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8") + b"\n"
    if len(texto) > MAX_BYTES:
        raise ValueError
    return texto


def _escribir_todo(fd: int, datos: bytes) -> None:
    vista = memoryview(datos)
    while vista:
        escritos = os.write(fd, vista)
        if escritos <= 0:
            raise OSError("escritura incompleta")
        vista = vista[escritos:]
