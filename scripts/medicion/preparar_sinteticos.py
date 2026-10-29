#!/usr/bin/env python3
"""Genera CBZ sintéticos para la medición E de #326.

No toca la biblioteca real: escribe en el directorio que se le pasa (el
orquestador lo crea fuera de la biblioteca y lo borra al terminar). Los
nombres son ficticios y deterministas.

Uso:
  python preparar_sinteticos.py --out DIR --prefix Viejos --count 100
  python preparar_sinteticos.py --out DIR --prefix Grandes --count 20 --size-mb 100
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
import zipfile
from pathlib import Path

from PIL import Image

MIB = 1024 * 1024


def _jpeg(indice: int, ancho: int = 500, alto: int = 750) -> bytes:
    # Ruido determinista: un color plano comprime a unos pocos bytes y no
    # representa el coste de leer/hashear una página de verdad.
    datos = random.Random(indice).randbytes(ancho * alto * 3)
    buf = io.BytesIO()
    Image.frombytes("RGB", (ancho, alto), datos).save(buf, "JPEG", quality=80)
    return buf.getvalue()


def _crear_cbz(destino: Path, indice: int, paginas: int, relleno_mb: int) -> int:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destino, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("portada.jpg", _jpeg(indice))
        for pagina in range(1, max(1, paginas)):
            zf.writestr(f"{pagina:03d}.jpg", _jpeg(indice * 100 + pagina))
        if relleno_mb > 0:
            info = zipfile.ZipInfo("relleno.bin")
            info.compress_type = zipfile.ZIP_STORED
            with zf.open(info, "w") as fh:
                bloque = b"\0" * MIB
                for _ in range(relleno_mb):
                    fh.write(bloque)
    destino.chmod(0o644)
    return destino.stat().st_size


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Genera CBZ sintéticos para la medición E (#326)")
    p.add_argument("--out", required=True, type=Path)
    p.add_argument("--prefix", required=True)
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--pages", type=int, default=12)
    p.add_argument("--size-mb", type=int, default=0)
    p.add_argument("--series", type=int, default=40)
    args = p.parse_args(argv)

    if args.count <= 0:
        print("--count debe ser positivo", file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    total = 0
    for i in range(args.start, args.start + args.count):
        serie = args.out / f"Serie {i % max(1, args.series):02d}"
        destino = serie / f"Titulo {i:05d}.cbz"
        total += _crear_cbz(destino, i, args.pages, args.size_mb)
    print(json.dumps({
        "schema": 1,
        "prefix": args.prefix,
        "files": args.count,
        "bytes": total,
        "pages": args.pages,
        "size_mb": args.size_mb,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
