#!/usr/bin/env python3
# ruff: noqa: E501
"""Comprobación DENTRO de la imagen de producción (dictamen de SecOps C-3 y C-4 sobre #455).

    docker run --rm --entrypoint runuser IMAGEN -u zascarr -- python /app/scripts/comprobar_imagen_rar.py

La suite de la CI prueba con el `unar` del ejecutor (v1.10.8); la imagen de producción, desde #528, es Debian trixie con
`unar`/`lsar` 1.10.8. Aquí se comprueba, con el `unar` de la imagen y como el usuario de servicio: que los ejecutables y
ficheros de servicio de `gnustep-base-runtime` ya no están (trixie añade `gdomap-helper`, `gdomap.service` y
`gdomap_probes`), que no hay ningún `setuid`/`setgid` nuevo, y que el lector lee los fixtures RAR (los tres legibles dan
portada; el RAR 5 sólido falla con `ilegible`, limitación conocida de `unar`) y que los seis RAR 4 hostiles de SecOps (N-1)
no escriben fuera del temporal, ni dan otra excepción que un motivo de dominio, ni dejan rastro, y dan el resultado
ESPERADO de cada caso. Imprime las versiones para dejar rastro. Sale con 1 si algo no cuadra.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))    # para `tests._rar_hostiles` (stdlib; viaja en la imagen)

from tests._rar_hostiles import CASOS, ESPERADO, generar  # noqa: E402
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
    print(_salida("dpkg-query", "-W", "-f", "${Package} ${Version}\\n", "unar", "gnustep-base-runtime", "libgnustep-base1.31"))

    # #530 C2: `lsar`/`unar` (GNUstep) invocan `dpkg-architecture` en runtime para DEB_HOST_MULTIARCH;
    # sin él abortan (SIGABRT) y el lector entero deja de funcionar. Y es un script Perl. La limpieza
    # de trixie borra ejecutables de construcción, pero estas dos piezas son dependencias de RUNTIME.
    for herramienta, motivo in (
            ("dpkg-architecture", "GNUstep lo invoca en runtime (DEB_HOST_MULTIARCH)"),
            ("perl", "dpkg-architecture es un script Perl")):
        if shutil.which(herramienta) is None:
            problemas.append(f"falta {herramienta}: {motivo}")

    ficheros = _salida("dpkg", "-L", "gnustep-base-runtime").splitlines()
    sobran = [f for f in ficheros if f.startswith(("/usr/bin/", "/usr/sbin/", "/etc/init.d/", "/etc/default/"))
              and Path(f).is_file()]
    # trixie mete además ficheros de servicio fuera de esas carpetas (helper, unit de systemd, sondas):
    # el Dockerfile los borra; aquí se exige que no quede ninguno por nombre del demonio.
    sobran += [f for f in ficheros if Path(f).is_file() and Path(f).name.startswith(("gdomap", "gdnc", "gpbs"))]
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
    # N-1 (SecOps): los seis RAR hostiles con el unar de ESTA imagen y como este usuario, con el mismo criterio que
    # `tests/test_lector_rar_real.py::test_rar_real_hostil_…`: nada fuera del temporal, el temporal se borra, ningún
    # nombre en el mensaje y solo `ErrorRar` como fallo.
    for caso in sorted(CASOS):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            ruta = generar(raiz / "entrada", caso)
            covers = raiz / "covers"
            covers.mkdir()
            antes = {str(p.relative_to(raiz)) for p in raiz.rglob("*")}
            try:
                portada_de_rar(ruta, covers, ancho=600)
                resultado = "portada"
            except ErrorRar as exc:
                resultado = exc.motivo.value
                if "secops" in str(exc).lower() or "passwd" in str(exc).lower():
                    problemas.append(f"hostil {caso}: el mensaje del error lleva un nombre")
            except Exception as exc:                       # noqa: BLE001
                problemas.append(f"hostil {caso}: excepción que no es ErrorRar: {type(exc).__name__}")
                continue
            nuevos = {str(p.relative_to(raiz)) for p in raiz.rglob("*")} - antes
            if nuevos - {"covers/.rar-tmp"}:
                problemas.append(f"hostil {caso}: escribió fuera del temporal: {sorted(nuevos)}")
            if (covers / ".rar-tmp").exists() and list((covers / ".rar-tmp").iterdir()):
                problemas.append(f"hostil {caso}: dejó un temporal")
            if resultado != ESPERADO[caso]:
                problemas.append(f"hostil {caso}: salió {resultado!r}, se esperaba {ESPERADO[caso]!r}")
            print(f"hostil {caso}: {resultado} (esperado {ESPERADO[caso]})")
    if list(Path("/tmp").glob("secops-*")):
        problemas.append("algún hostil escribió en /tmp fuera del destino")
    print("uid:", os.getuid())
    for p in problemas:
        print(f"::error::{p}", file=sys.stderr)
    return 1 if problemas else 0


if __name__ == "__main__":
    raise SystemExit(main())
