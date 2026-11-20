"""Registro experimental antirrepetición de OPS4; no instalado ni conectado.

Un directorio ya provisionado por el host contiene marcas permanentes por ID.
No es la reserva de operación, no adquiere el cerrojo de copia/restauración y
no autoriza lanzar nada. La retención/capacidad y la identidad del directorio
siguen pendientes: no se borran marcas automáticamente. Un disco lleno deniega.
"""
from __future__ import annotations

import contextlib
import os
import re
import stat
from collections.abc import Callable

_ID = re.compile(r"[0-9a-f]{32}\Z")


class RegistroNoDisponibleError(Exception):
    """Persistencia no acreditada; no autoriza efectos ni reutilización del ID."""


def reclamar_id(
    id_: object,
    *,
    directorio_fd: int,
    sincronizar: Callable[[int], None] = os.fsync,
) -> bool:
    """True solo tras creación exclusiva y fsync de marca y directorio.

    False significa que el nombre ya existe (también un enlace o una marca
    incompleta). Cualquier otro fallo eleva una excepción sin secretos. El
    llamador aporta un descriptor de directorio confiable; se duplica para
    anclar todas las operaciones sin resolver de nuevo su ruta. No se acredita
    aquí procedencia, propiedad esperada ni seguridad de la jerarquía del host.
    """
    if not isinstance(id_, str) or not _ID.fullmatch(id_):
        raise RegistroNoDisponibleError("identificador no válido")
    if type(directorio_fd) is not int or directorio_fd < 0:
        raise RegistroNoDisponibleError("directorio no disponible")
    directory = None
    marker = None
    try:
        directory = os.dup(directorio_fd)
        info = os.fstat(directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o022:
            raise RegistroNoDisponibleError("directorio no seguro")
        try:
            marker = os.open(
                f"solicitud-{id_}",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600, dir_fd=directory,
            )
        except FileExistsError:
            return False
        # La propia existencia de la marca vacía consume el ID. No contiene
        # contraseña, hash, firma ni estado de la operación.
        if sincronizar(marker) is not None or sincronizar(directory) is not None:
            raise RegistroNoDisponibleError("sincronización no acreditada")
        closing, marker = marker, None
        os.close(closing)
        closing, directory = directory, None
        os.close(closing)
        return True
    except RegistroNoDisponibleError:
        raise
    except Exception:
        raise RegistroNoDisponibleError("persistencia no disponible") from None
    finally:
        # No deshacer una creación aunque falle fsync: su resultado es incierto.
        # close no reintenta ni modifica el nombre de la marca.
        if marker is not None:
            with contextlib.suppress(OSError):
                os.close(marker)
        if directory is not None:
            with contextlib.suppress(OSError):
                os.close(directory)
