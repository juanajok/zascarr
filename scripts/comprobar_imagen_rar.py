#!/usr/bin/env python3
# ruff: noqa: E501
"""Comprobación DENTRO de la imagen de producción (dictamen de SecOps C-3 y C-4 sobre #455).

    docker run --rm --entrypoint runuser IMAGEN -u zascarr -- python /app/scripts/comprobar_imagen_rar.py

La suite de la CI prueba con el `unar` del ejecutor (v1.10.8); la imagen lleva el de Debian bookworm (v1.10.1). Aquí se
comprueba, con el `unar` de la imagen y como el usuario de servicio: que los ejecutables de `gnustep-base-runtime` ya no
están, que no hay ningún `setuid`/`setgid` nuevo, y que el lector lee los fixtures RAR (los tres legibles dan portada; el
RAR 5 sólido falla con `ilegible`, limitación conocida de `unar`). Imprime las versiones para dejar rastro. Sale con 1 si algo no cuadra.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from zascarr.models import MotivoRar
from zascarr.utils.lector_rar import ErrorRar
from zascarr.utils.portada_rar import portada_de_rar

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "rar"
LEGIBLES = ("minimo_rar4.cbr", "minimo_rar5.cbr", "solido_rar4.cbr")
SETUID_DE_LA_BASE = {"chage", "chfn", "chsh", "expiry", "gpasswd", "mount", "newgrp", "passwd", "su", "umount", "unix_chkpwd"}


def _salida(*orden: str) -> str:
    return subprocess.run(orden, capture_output=True, text=True, check=False).stdout.strip()   # noqa: S603


def main() -> int:
    problemas: list[str] = []
    print("unar:", _salida("unar", "-v"), "| lsar:", _salida("lsar", "-v"))
    print(_salida("dpkg-query", "-W", "-f", "${Package} ${Version}\\n", "unar", "gnustep-base-runtime", "libgnustep-base1.28"))

    ficheros = _salida("dpkg", "-L", "gnustep-base-runtime").splitlines()
    sobran = [f for f in ficheros if f.startswith(("/usr/bin/", "/usr/sbin/", "/etc/init.d/", "/etc/default/"))
              and Path(f).is_file()]
    if sobran:
        problemas.append(f"quedan ejecutables de gnustep-base-runtime: {sobran}")

    setuid = _salida("find", "/", "-xdev", "-perm", "/6000", "-type", "f").splitlines()
    nuevos = [f for f in setuid if Path(f).name not in SETUID_DE_LA_BASE]
    if nuevos:
        problemas.append(f"setuid/setgid fuera de la base de Debian: {nuevos}")

    with tempfile.TemporaryDirectory() as tmp:
        covers = Path(tmp)
        for nombre in LEGIBLES:
            try:
                jpeg, _ = portada_de_rar(FIXTURES / nombre, covers, ancho=600)
                print(f"{nombre}: portada de {len(jpeg)} B")
            except ErrorRar as exc:
                problemas.append(f"{nombre}: no se leyó ({exc.motivo.value})")
        try:
            portada_de_rar(FIXTURES / "solido_rar5.cbr", covers, ancho=600)
            problemas.append("solido_rar5.cbr SÍ se leyó: la limitación de unar ya no existe; revisar la decisión del PO (FR-33)")
        except ErrorRar as exc:
            if exc.motivo is not MotivoRar.ILEGIBLE:
                problemas.append(f"solido_rar5.cbr: motivo inesperado {exc.motivo.value}")
            print("solido_rar5.cbr: ilegible (limitación conocida de unar)")
    print("uid:", os.getuid())
    for p in problemas:
        print(f"::error::{p}", file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
