# ruff: noqa: E501
"""Una «VM» de mentira para probar el ciclo de vida del arnés SIN arrancar QEMU.

Lanza un proceso desacoplado cuyo `argv[0]` termina en `qemu-system-x86_64` y cuyos argumentos llevan `-name <nombre>` y
`file=<dir>/…` (lo que el arnés mira para reconocer SU VM), escribe su PID en un fichero (como `-pidfile` de QEMU) y sale.
Uso: python tests/_vm_falsa.py PIDFILE DIR [--ignora-term] [--nombre NOMBRE] [--sin-disco]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def lanzar(pidfile: Path, directorio: Path, *, ignora_term: bool = False, nombre: str = "m4-f1bis",
           con_disco: bool = True, ejecutable: str = "qemu-system-x86_64") -> int:
    bin_dir = directorio / "bin-falso"
    bin_dir.mkdir(parents=True, exist_ok=True)
    guion = ('trap "" TERM; ' if ignora_term else "") + "while :; do sleep 0.2; done"
    args = [str(bin_dir / ejecutable), "-c", guion, "-name", nombre]
    if con_disco:
        args.append(f"file={directorio}/f1bis-ejec.qcow2,if=virtio")
    p = subprocess.Popen(args, executable="/bin/bash", start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pidfile.write_text(f"{p.pid}\n")
    return p.pid


if __name__ == "__main__":
    pidfile, directorio = Path(sys.argv[1]), Path(sys.argv[2])
    lanzar(pidfile, directorio, ignora_term="--ignora-term" in sys.argv, con_disco="--sin-disco" not in sys.argv,
           nombre=sys.argv[sys.argv.index("--nombre") + 1] if "--nombre" in sys.argv else "m4-f1bis")
