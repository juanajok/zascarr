"""Cerrojo de admisión de OPS4: serializa auxiliares, no operaciones.

No es el cerrojo de operaciones (`/run/zascarr-ops.lock`), no se mantiene
durante la actualización y no autoriza ningún efecto. Solo evita que dos
auxiliares escriban dos reservas a la vez. El descriptor se libera al cerrarlo.
"""
from __future__ import annotations

import fcntl
import os
import stat


def tomar_admision(ruta: object) -> int | None:
    """Toma el `flock` exclusivo no bloqueante; `None` si ya está ocupado.

    El fichero se crea `0600` sin seguir enlaces. `None` solo significa que otro
    auxiliar lo tiene; cualquier otro error se eleva al llamador, que debe
    fallar cerrado.
    """
    fd = os.open(
        os.fspath(ruta),
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise OSError("la admisión no es un fichero regular")
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            return None
    except BaseException:
        os.close(fd)
        raise
    return fd


def liberar_admision(fd: int) -> None:
    """Cierra el descriptor; el cerrojo se libera con él."""
    os.close(fd)
