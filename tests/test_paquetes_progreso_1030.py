"""#1030: la extracción del paquete informa por ítem al indicador global."""
from __future__ import annotations

import os
import zipfile

from zascarr.services.paquetes import EntradaPaquete, ListadoPaquete
from zascarr.services.paquetes_extraccion import _escribir_zip


def test_escribir_zip_informa_cada_item(tmp_path):
    paquete = tmp_path / "p.zip"
    with zipfile.ZipFile(paquete, "w") as z:
        z.writestr("a.cbz", b"a" * 10)
        z.writestr("b.cbz", b"b" * 10)
    listado = ListadoPaquete(
        paquete=None, formato="ZIP",
        entradas=(EntradaPaquete("a.cbz", 10, "cbz", True),
                  EntradaPaquete("b.cbz", 10, "cbz", True)),
        ignoradas=(), bytes_estimados=20)
    vistos: list[int] = []
    fd = os.open(paquete, os.O_RDONLY)
    temp = tmp_path / "temp"
    temp.mkdir()
    temp_fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY)
    try:
        items = _escribir_zip(None, listado, temp, fd, temp_fd,
                              lambda n: vistos.append(n))
    finally:
        os.close(fd)
        os.close(temp_fd)
    assert len(items) == 2
    assert vistos == [1, 2]
