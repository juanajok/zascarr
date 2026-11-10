#!/usr/bin/env python3
"""CLI de BL-ETQ2b (#573): relectura del ComicInfo de la biblioteca registrada.

Uso (dentro del contenedor; desde el host, `scripts/backfill-comicinfo.sh`):

    python - --dry-run     # informe, sin escribir (defecto)
    python - --aplicar     # aplica (idempotente)

La lógica vive en `zascarr.services.backfill_comicinfo`; este fichero solo parsea los argumentos.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from zascarr.services.backfill_comicinfo import ejecutar, imprimir


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Relee el ComicInfo de los CBZ registrados y aplica ETQ2 "
                    "(solo lectura de ficheros).")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--dry-run", action="store_true", help="informe sin escribir (defecto)")
    grupo.add_argument("--aplicar", action="store_true", help="aplica los cambios (idempotente)")
    parser.add_argument("--limite", type=int, default=None,
                        help="procesa como mucho N ficheros (pruebas)")
    args = parser.parse_args()
    try:
        informe = asyncio.run(ejecutar(aplicar=args.aplicar, limite=args.limite))
    except Exception as exc:  # noqa: BLE001 — el operador ve causa corta, sin traza
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    imprimir(informe)
    if not informe.cerrojo:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
