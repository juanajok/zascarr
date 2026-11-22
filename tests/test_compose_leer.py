"""Regresión: `update.sh` se quedó parado en la Pi (2026-11-22) leyendo `BUILD_SHA`.

Mecanismo: `docker compose exec` lee stdin aunque lleve `-T`; `timeout` lanza la orden en
segundo plano, así que, con `update.sh` en una terminal, leer de ella la detenía (SIGTTIN). El
cliente ignoraba el SIGTERM del `timeout 5` y la sustitución `$(...)` esperaba para siempre,
sin ningún mensaje.

Las pruebas ejecutan las funciones de `scripts/_comun.sh` con una terminal real (pty como
terminal de control) y un `docker` de pega que se comporta igual: lee stdin e ignora SIGTERM.
"""
from __future__ import annotations

import fcntl
import os
import pty
import subprocess
import sys
import termios
import time
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SHA = "a" * 40

DOCKER_QUE_LEE_STDIN = f"""#!/usr/bin/env bash
trap '' TERM
if [[ "$*" == *"printenv BUILD_SHA"* || "$*" == *psql* ]]; then
    cat >/dev/null 2>&1 || true
    [[ "$*" == *psql* ]] && echo "0052" || echo "{SHA}"
fi
"""

DOCKER_QUE_NO_TERMINA = """#!/usr/bin/env bash
trap '' TERM
while :; do sleep 1; done
"""

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")


def _con_terminal(tmp_path: Path, docker: str, funcion: str, limite: float) -> tuple[str, float]:
    """Ejecuta `funcion` de `_comun.sh` con un pty como terminal de control y stdin."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(docker, encoding="utf-8")
    (bin_dir / "docker").chmod(0o755)
    salida = tmp_path / "salida"
    guion = (
        "set -euo pipefail\n"
        f"REPO_DIR={RAIZ}\n"
        f"ENV_FILE={tmp_path / '.env'}\n"
        "DB_USER=zascarr\nDB_NAME=zascarr\n"
        f"source {RAIZ / 'scripts' / '_comun.sh'}\n"
        f"{funcion} > {salida}\n"
    )
    maestro, esclavo = pty.openpty()

    def _terminal_de_control() -> None:
        fcntl.ioctl(0, termios.TIOCSCTTY, 0)

    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    inicio = time.monotonic()
    proc = subprocess.Popen(
        ["bash", "-c", guion], stdin=esclavo, stdout=esclavo, stderr=esclavo,
        start_new_session=True, preexec_fn=_terminal_de_control, env=env,
    )
    os.close(esclavo)
    try:
        proc.wait(timeout=limite)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, 9)
        proc.wait()
        pytest.fail(f"`{funcion}` se quedó colgada más de {limite:.0f} s con una terminal")
    finally:
        os.close(maestro)
    assert proc.returncode == 0
    return salida.read_text(encoding="utf-8"), time.monotonic() - inicio


def test_leer_build_sha_no_se_detiene_al_leer_la_terminal(tmp_path):
    """Causa del cuelgue: con `</dev/null` el cliente no toca la terminal y responde ya."""
    valor, duracion = _con_terminal(tmp_path, DOCKER_QUE_LEE_STDIN, "leer_build_sha", limite=20)
    assert valor == SHA
    assert duracion < 4


def test_leer_revision_alembic_no_se_detiene_al_leer_la_terminal(tmp_path):
    valor, _ = _con_terminal(tmp_path, DOCKER_QUE_LEE_STDIN, "leer_revision_alembic", limite=20)
    assert valor == "0052"


def test_un_cliente_que_ignora_sigterm_se_remata_y_la_copia_sigue(tmp_path):
    """`timeout -k`: si ignora el aviso, SIGKILL al grupo; el dato queda vacío (`null`)."""
    valor, duracion = _con_terminal(tmp_path, DOCKER_QUE_NO_TERMINA, "leer_build_sha", limite=30)
    assert valor == ""
    assert duracion < 15
