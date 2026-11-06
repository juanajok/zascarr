#!/usr/bin/env python3
# ruff: noqa: E501
"""Apoyo del job «Suite unitaria» de la CI: exige que las pruebas con RAR real SE EJECUTARON (#418).

    ci_rar_real.py INFORME.xml

Las pruebas de `tests/test_lector_rar_real.py` se saltan solas si falta `unar` o un fixture; un job que
instalara mal `unar` quedaría verde sin haber leído ni un RAR. Aquí «verde» exige un mínimo de pruebas
ejecutadas de ese fichero y **cero** saltadas, con fallos o con errores (mismo patrón que
`scripts/ci_postgres.py`). Solo stdlib.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

FICHERO = "test_lector_rar_real"
#: 3 + 3 + 1 + 1 (ver el fichero). Bajarlo es una decisión consciente, no un descuido.
MINIMO_DE_PRUEBAS = 8


def motivos(ruta: str, minimo: int = MINIMO_DE_PRUEBAS) -> list[str]:
    raiz = ET.parse(ruta).getroot()
    casos = [c for c in raiz.iter("testcase") if FICHERO in c.get("classname", "")]
    saltadas = [c for c in casos if c.find("skipped") is not None]
    rotas = [c for c in casos if c.find("failure") is not None or c.find("error") is not None]
    out = []
    if len(casos) < minimo:
        out.append(f"solo {len(casos)} pruebas de RAR real en el informe (mínimo {minimo})")
    if saltadas:
        out.append(f"{len(saltadas)} pruebas de RAR real saltadas (¿falta `unar` o un fixture?)")
    if rotas:
        out.append(f"{len(rotas)} pruebas de RAR real con fallo o error")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    problemas = motivos(args[0])
    for p in problemas:
        print(f"::error::{p}", file=sys.stderr)
    if not problemas:
        print("Las pruebas de RAR real se ejecutaron (ninguna saltada).")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
