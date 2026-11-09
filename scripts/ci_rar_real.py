#!/usr/bin/env python3
# ruff: noqa: E501
"""Apoyo del job «Suite unitaria» de la CI: exige RAR real ejecutado y la herramienta correcta (#418, #530).

    ci_rar_real.py INFORME.xml

Las pruebas de `tests/test_lector_rar_real.py` se saltan solas si falta `unar` o un fixture; un job que
instalara mal `unar` quedaría verde sin haber leído ni un RAR. Aquí «verde» exige un mínimo de pruebas
ejecutadas de ese fichero y **cero** saltadas, con fallos o con errores (mismo patrón que
`scripts/ci_postgres.py`). Además (#530 C3) exige `unar`/`lsar` **1.10.8** y el flag
`-json-skip-solid-information`: el fallback de `listar` no puede tapar un runner antiguo (1.10.1 no
conoce el flag) y convertir en verde lo que no es el entorno de producción. Solo stdlib.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

FICHERO = "test_lector_rar_real"
#: 3 + 3 + 1 (xfail estricto) + 1 + 1 + 7 hostiles + 1 del enlace (ver el fichero). Bajarlo es una decisión consciente.
MINIMO_DE_PRUEBAS = 17
#: Versión y flag que exige la imagen de producción desde #528/#530.
VERSION_EXIGIDA = "1.10.8"
FLAG_SOLIDOS = "-json-skip-solid-information"


def motivos(ruta: str, minimo: int = MINIMO_DE_PRUEBAS) -> list[str]:
    raiz = ET.parse(ruta).getroot()
    casos = [c for c in raiz.iter("testcase") if FICHERO in c.get("classname", "")]
    # un `xfail` (fallo esperado, estricto) figura en el informe como «skipped» de tipo `pytest.xfail`: se
    # EJECUTÓ y falló como se esperaba, no es una prueba saltada
    saltadas = [c for c in casos
                if c.find("skipped") is not None and c.find("skipped").get("type") != "pytest.xfail"]
    rotas = [c for c in casos if c.find("failure") is not None or c.find("error") is not None]
    out = []
    if len(casos) < minimo:
        out.append(f"solo {len(casos)} pruebas de RAR real en el informe (mínimo {minimo})")
    if saltadas:
        out.append(f"{len(saltadas)} pruebas de RAR real saltadas (¿falta `unar` o un fixture?)")
    if rotas:
        out.append(f"{len(rotas)} pruebas de RAR real con fallo o error")
    return out


def _salida(*orden: str) -> str:
    p = subprocess.run(orden, capture_output=True, text=True, check=False)  # noqa: S603
    return p.stdout + p.stderr


def problemas_de_la_herramienta() -> list[str]:
    """El runner de la suite tiene que ser el de producción (#530 C3): `unar`/`lsar` 1.10.8 y el flag."""
    out: list[str] = []
    for nombre in ("unar", "lsar"):
        ruta = shutil.which(nombre)
        if ruta is None:
            out.append(f"falta {nombre} en el PATH")
            continue
        version = _salida(ruta, "-v").strip()
        if VERSION_EXIGIDA not in version:
            out.append(f"{nombre} no es {VERSION_EXIGIDA} ({version or 'sin versión'})")
    lsar = shutil.which("lsar")
    if lsar is not None and FLAG_SOLIDOS not in _salida(lsar, "--help"):
        out.append(f"lsar no conoce {FLAG_SOLIDOS}")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    problemas = motivos(args[0]) + problemas_de_la_herramienta()
    for p in problemas:
        print(f"::error::{p}", file=sys.stderr)
    if not problemas:
        print("Las pruebas de RAR real se ejecutaron con unar/lsar 1.10.8 y el flag (ninguna saltada).")
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
