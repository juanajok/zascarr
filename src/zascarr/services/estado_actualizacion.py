"""Lector aislado del futuro estado informativo de actualización (#443).

Contrato propuesto, no hay escritor ni operación de actualización implementados:
JSON UTF-8 de hasta 4096 bytes, objeto cerrado con ``schema`` (entero 1),
``id`` (32 hexadecimales minúsculos), ``estado`` (aceptada, en_curso, hecha,
fallida o incierta), ``inicio_epoch`` y ``actualizado_epoch`` (segundos Unix
enteros). Los tiempos deben estar ordenados y no ser futuros. Una operación
activa sin noticias durante 600 segundos se considera incierta. El id esperado
es obligatorio: un estado anterior nunca se atribuye a otro intento.

Esto es únicamente información declarada por un hipotético escritor del host:
no acredita su procedencia, éxito efectivo, seguridad ni autorización para
iniciar, repetir o recuperar una operación. La integración deberá proteger el
archivo y directorios y reconciliar el host ante cualquier incertidumbre.
No se devuelven datos libres del archivo ni errores, rutas o identificadores.
"""
from __future__ import annotations

import json
import os
import re
import stat
import time
from enum import StrEnum
from pathlib import Path
from typing import Any

MAX_BYTES = 4096
#: El ejecutor permite 5400 s; el margen evita declarar incierta una obra sana.
SIN_NOTICIAS_SEGUNDOS = 7200
_ID = re.compile(r"[0-9a-f]{32}\Z")
_CAMPOS = {"schema", "id", "estado", "inicio_epoch", "actualizado_epoch"}


class EstadoActualizacion(StrEnum):
    """Categorías cerradas, sin mensajes proporcionados por el host."""

    ACEPTADA = "aceptada"
    EN_CURSO = "en_curso"
    HECHA = "hecha"
    FALLIDA = "fallida"
    INCIERTA = "incierta"


def _objeto_sin_duplicados(pares: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pares:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _abrir_regular(path: Path) -> int:
    """Abre cada componente sin seguir enlaces; nunca espera a un FIFO."""
    parts = path.parts
    if not parts or any(part in ("..", "") for part in parts):
        raise ValueError
    flags_dir = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_NONBLOCK
    current = os.open("/" if path.is_absolute() else ".", flags_dir)
    try:
        components = parts[1:] if path.is_absolute() else parts
        if not components:
            raise ValueError
        for part in components[:-1]:
            next_fd = os.open(part, flags_dir, dir_fd=current)
            os.close(current)
            current = next_fd
        # O_PATH permite inspeccionar el tipo sin abrir un dispositivo o FIFO.
        # El acceso posterior por /proc/self/fd ancla el mismo inode, incluso si
        # se sustituye la entrada del directorio. Si proc no está disponible,
        # la lectura falla cerrada; esto no acredita propiedad ni procedencia.
        anchor = os.open(components[-1], os.O_PATH | os.O_NOFOLLOW, dir_fd=current)
        try:
            expected = os.fstat(anchor)
            if not stat.S_ISREG(expected.st_mode):
                raise ValueError
            fd = os.open(f"/proc/self/fd/{anchor}", os.O_RDONLY | os.O_NONBLOCK)
            try:
                actual = os.fstat(fd)
                if (actual.st_dev, actual.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError
                return fd
            except BaseException:
                os.close(fd)
                raise
        finally:
            os.close(anchor)
    finally:
        os.close(current)


def leer_estado_actualizacion(
    path: Path, *, id_esperado: str, ahora_epoch: int | None = None
) -> EstadoActualizacion:
    """Lee una instantánea correlacionada o devuelve siempre incertidumbre.

    El reloj puede inyectarse para las pruebas; un reloj inválido falla cerrado.
    La lectura es síncrona y quien la integre en una vista async debe delegarla.
    """
    if not isinstance(id_esperado, str) or not _ID.fullmatch(id_esperado):
        return EstadoActualizacion.INCIERTA
    if ahora_epoch is None:
        ahora_epoch = int(time.time())
    if type(ahora_epoch) is not int or not 0 <= ahora_epoch < 2**63:
        return EstadoActualizacion.INCIERTA
    try:
        fd = _abrir_regular(Path(path))
        try:
            before = os.fstat(fd)
            if before.st_size > MAX_BYTES:
                return EstadoActualizacion.INCIERTA
            data = bytearray()
            while len(data) <= MAX_BYTES:
                chunk = os.read(fd, MAX_BYTES + 1 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
            after = os.fstat(fd)
            if (len(data) > MAX_BYTES or len(data) != after.st_size
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                    != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
                return EstadoActualizacion.INCIERTA
        finally:
            os.close(fd)
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_objeto_sin_duplicados)
        if type(obj) is not dict or set(obj) != _CAMPOS:
            return EstadoActualizacion.INCIERTA
        if type(obj["schema"]) is not int or obj["schema"] != 1 or obj["id"] != id_esperado:
            return EstadoActualizacion.INCIERTA
        start, updated = obj["inicio_epoch"], obj["actualizado_epoch"]
        if (type(start) is not int or type(updated) is not int
                or not 0 <= start <= updated <= ahora_epoch):
            return EstadoActualizacion.INCIERTA
        if type(obj["estado"]) is not str:
            return EstadoActualizacion.INCIERTA
        state = EstadoActualizacion(obj["estado"])
        if (state in (EstadoActualizacion.ACEPTADA, EstadoActualizacion.EN_CURSO)
                and ahora_epoch - updated >= SIN_NOTICIAS_SEGUNDOS):
            return EstadoActualizacion.INCIERTA
        return state
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError, OverflowError):
        return EstadoActualizacion.INCIERTA
