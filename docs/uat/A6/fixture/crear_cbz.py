#!/usr/bin/env python3
"""Genera CBZ deterministas para A6 (stdlib, sin dependencias).

Uso: python3 crear_cbz.py <salida_dir>
Escribe ARCHIVO-A.cbz (6 páginas) y ARCHIVO-B.cbz (3 páginas).
Cada página es un PNG RGB 140x200 de color plano distinto y bytes estables.
"""
from __future__ import annotations

import pathlib
import struct
import sys
import zipfile
import zlib


def png(ancho: int, alto: int, rgb: tuple[int, int, int]) -> bytes:
    firma = b"\x89PNG\r\n\x1a\n"

    def trozo(tipo: bytes, datos: bytes) -> bytes:
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    fila = b"\x00" + bytes(rgb) * ancho
    idat = zlib.compress(fila * alto, 9)
    return firma + trozo(b"IHDR", ihdr) + trozo(b"IDAT", idat) + trozo(b"IEND", b"")


def crear(destino: pathlib.Path, paginas: int, base: tuple[int, int, int]) -> None:
    with zipfile.ZipFile(destino, "w", zipfile.ZIP_STORED) as zf:
        for n in range(1, paginas + 1):
            color = tuple(min(255, c + n * 17) for c in base)
            info = zipfile.ZipInfo(f"pagina-{n:03d}.png", date_time=(2026, 11, 22, 12, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            zf.writestr(info, png(140, 200, color))


def main() -> int:
    salida = pathlib.Path(sys.argv[1])
    salida.mkdir(parents=True, exist_ok=True)
    crear(salida / "ARCHIVO-A.cbz", 6, (30, 60, 120))
    crear(salida / "ARCHIVO-B.cbz", 3, (120, 40, 30))
    print(f"CBZ generados en {salida.name}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
