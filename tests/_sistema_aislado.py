"""Un sistema aislado y desechable donde ejecutar guiones como `root` con usuarios sintéticos.

Las pruebas de **credenciales** (PR de inicialización y protección del `.env`) tienen que comprobar permisos de
verdad: «el usuario de servicio no puede reemplazar el fichero» solo se demuestra intentándolo **como ese usuario**,
y eso exige `root` para crearlo. Nada de esto debe tocar la máquina de quien ejecuta las pruebas, así que:

| Modo | Cuándo | Qué es |
|---|---|---|
| `directo` | la prueba ya corre como `root` | el propio sistema (solo en una máquina desechable) |
| `ci` | variable `CI=true` y `sudo -n` disponible | el ejecutor de GitHub Actions: una VM nueva por trabajo |
| `docker` | hay un demonio y la imagen `debian:12` **ya descargada** | un contenedor `--rm --network none` |

Si ninguno está disponible, la prueba **se salta** (y el informe de la PR la cuenta como «no ejecutada»: una prueba
saltada no es una prueba pasada). Los guiones imprimen líneas `PASS id detalle` / `FAIL id detalle`; **nunca** valores
de credenciales (solo longitudes, huellas y modos).
"""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESCENARIOS = RAIZ / "tests" / "escenarios"
IMAGEN = os.environ.get("ZASCARR_PRUEBAS_IMAGEN", "debian:12")


@dataclass
class Resultado:
    modo: str
    returncode: int
    stdout: str
    stderr: str
    casos: dict[str, tuple[str, str]]       # id -> (PASS|FAIL, detalle)


def _docker_con_imagen() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(["docker", "image", "inspect", IMAGEN], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0


def _sudo_sin_clave() -> bool:
    if shutil.which("sudo") is None:
        return False
    try:
        return subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=10, check=False).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def modo_disponible() -> str | None:
    if os.geteuid() == 0:
        return "directo"
    if os.environ.get("CI") == "true" and _sudo_sin_clave():
        return "ci"
    if _docker_con_imagen():
        return "docker"
    return None


MOTIVO_SALTO = (
    "NO EJECUTADA: hace falta un sistema desechable con root (ser root, CI=true con sudo sin clave, o Docker con la "
    f"imagen {IMAGEN} ya descargada)"
)


def _casos(salida: str) -> dict[str, tuple[str, str]]:
    casos: dict[str, tuple[str, str]] = {}
    for linea in salida.splitlines():
        partes = linea.split(" ", 2)
        if len(partes) >= 2 and partes[0] in ("PASS", "FAIL"):
            casos[partes[1]] = (partes[0], partes[2] if len(partes) > 2 else "")
    return casos


def ejecutar(escenario: str, *, timeout: int = 300) -> Resultado:
    """Ejecuta `tests/escenarios/<escenario>` como root en un sistema desechable. Salta si no hay ninguno."""
    import pytest

    modo = modo_disponible()
    if modo is None:
        pytest.skip(MOTIVO_SALTO)
    guion = ESCENARIOS / escenario
    if modo == "docker":
        orden = ["docker", "run", "--rm", "--network", "none", "--pull", "never",
                 "-v", f"{RAIZ}:/repo:ro", "-e", "REPO=/repo", IMAGEN, "bash", f"/repo/tests/escenarios/{escenario}"]
    elif modo == "ci":
        orden = ["sudo", "-n", "env", f"REPO={RAIZ}", "bash", str(guion)]
    else:
        orden = ["env", f"REPO={RAIZ}", "bash", str(guion)]
    r = subprocess.run(orden, capture_output=True, text=True, timeout=timeout, check=False)
    return Resultado(modo, r.returncode, r.stdout, r.stderr, _casos(r.stdout))
