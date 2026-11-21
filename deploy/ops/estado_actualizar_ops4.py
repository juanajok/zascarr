#!/usr/bin/env python3
"""Marca el resultado final de la unidad de actualización; no ejecuta nada.

Uso fijo desde la unidad:
  zascarr-estado-actualizar-ops4 --ruta ... --resultado hecha|fallida|incierta

Conserva el id y `inicio_epoch` del estado que escribió el auxiliar. Si no hay
estado válido, sale 0 sin inventar uno: la unidad no debe fallar por no poder
anotar una fase. No acepta texto libre ni imprime el estado.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))

from escritor_estado_actualizar_ops4 import (  # noqa: E402
    ResultadoEscritura,
    escribir_estado,
)

_ID = re.compile(r"[0-9a-f]{32}\Z")
_RESULTADOS = {"hecha", "fallida", "incierta"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--ruta", required=True)
    parser.add_argument("--resultado", required=True)
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return 2
    if args.resultado not in _RESULTADOS:
        return 2
    try:
        with open(args.ruta, encoding="utf-8") as fh:
            datos = json.load(fh)
        if (
            type(datos) is not dict
            or set(datos) != {"schema", "id", "estado", "inicio_epoch", "actualizado_epoch"}
            or type(datos["id"]) is not str
            or not _ID.fullmatch(datos["id"])
            or type(datos["inicio_epoch"]) is not int
            or not 0 <= datos["inicio_epoch"] <= int(time.time())
        ):
            return 0
    except (OSError, ValueError, TypeError):
        return 0
    datos["estado"] = args.resultado
    datos["actualizado_epoch"] = int(time.time())
    if escribir_estado(args.ruta, datos) is not ResultadoEscritura.OK:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
