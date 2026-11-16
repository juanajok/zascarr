"""Worker de extracción ZIP aislado en proceso propio (#344).

El padre le pasa el fd ya abierto del paquete y una carpeta temporal; el hijo no hereda más fds y
solo escribe en esa carpeta. Si el padre lo mata por timeout, el grupo entero muere.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from zascarr.services import paquetes_extraccion as extraccion
from zascarr.services.paquetes import PaquetePendiente, listar_paquete
from zascarr.services.paquetes_extraccion import _escribir_zip, _verificar_contenido


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 3:
        return 2
    datos = json.loads(args[0])
    extraccion.MAX_BYTES_ENTRADA = int(datos["max_entrada"])
    extraccion.MAX_BYTES_TOTAL = int(datos["max_total"])
    extraccion.MAX_RATIO_LEIDA = int(datos["max_ratio"])
    fd = int(args[1])
    temp = Path(args[2])
    paquete = PaquetePendiente(
        ruta=Path(f"/proc/self/fd/{fd}"), raiz=temp, relativa=datos["nombre"],
        nombre=datos["nombre"], tamano=int(datos["tamano"]), mtime_ns=int(datos["mtime_ns"]),
        firma=datos["firma"], estado="listo", causa="", dev=int(datos["dev"]),
        ino=int(datos["ino"]), fd=fd)
    listado = listar_paquete(paquete)
    temp_fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        items = _escribir_zip(paquete, listado, temp, fd, temp_fd)
        _verificar_contenido(items, temp, temp_fd)
    finally:
        os.close(temp_fd)
    sys.stdout.write(json.dumps(items, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
