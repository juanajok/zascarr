"""Worker de extracción ZIP aislado en proceso propio (#344).

El padre le pasa el fd ya abierto del paquete y una carpeta temporal; el hijo no hereda más fds y
solo escribe en esa carpeta. Si el padre lo mata por timeout, el grupo entero muere.
"""
from __future__ import annotations

import contextlib
import json
import os
import resource
import sys
from pathlib import Path

from zascarr.services import paquetes_extraccion as extraccion
from zascarr.services.paquetes import PaquetePendiente, listar_paquete
from zascarr.services.paquetes_extraccion import (
    _escribir_rar,
    _escribir_zip,
    _verificar_contenido,
)


def main(argv: list[str] | None = None) -> int:
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024,
                                               512 * 1024 * 1024))
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 5:
        return 2
    datos = json.loads(args[0])
    extraccion.MAX_BYTES_ENTRADA = int(datos["max_entrada"])
    extraccion.MAX_BYTES_TOTAL = int(datos["max_total"])
    extraccion.MAX_RATIO_LEIDA = int(datos["max_ratio"])
    modo = args[1]
    fd = int(args[2])
    temp = Path(args[3])
    temp_fd = int(args[4])
    paquete = PaquetePendiente(
        ruta=Path(f"/proc/self/fd/{fd}"), raiz=temp, relativa=datos["nombre"],
        nombre=datos["nombre"], tamano=int(datos["tamano"]), mtime_ns=int(datos["mtime_ns"]),
        firma=datos["firma"], estado="listo", causa="", dev=int(datos["dev"]),
        ino=int(datos["ino"]), fd=fd)
    listado = listar_paquete(paquete)

    def _progreso(hechos: int) -> None:
        with contextlib.suppress(OSError):
            fd_p = os.open(".progreso", os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                           0o600, dir_fd=temp_fd)
            try:
                os.write(fd_p, str(hechos).encode("ascii"))
            finally:
                os.close(fd_p)

    try:
        if modo == "zip":
            items = _escribir_zip(paquete, listado, temp, fd, temp_fd, _progreso)
        else:
            items = _escribir_rar(paquete, listado, temp, fd, temp_fd, _progreso)
        with contextlib.suppress(OSError):
            os.unlink(".progreso", dir_fd=temp_fd)
        _verificar_contenido(items, temp, temp_fd)
    finally:
        os.close(temp_fd)
    sys.stdout.write(json.dumps(items, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
