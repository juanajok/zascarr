"""Sondeo sintético de cgroup: solo para una VM desechable, nunca producción.

El hijo cambia de sesión e ignora SIGTERM. Ningún proceso realiza operaciones
sobre la aplicación, Docker, la BD ni la red. systemd debe matarlos al vencer
RuntimeMaxSec. Los PID se guardan únicamente en RuntimeDirectory de la unidad.
"""
from __future__ import annotations

import os
import signal
from pathlib import Path

DIRECTORY = Path("/run/ops4-lab-timeout")


def main() -> None:
    """Espera indefinidamente; el vigilante externo debe detener padre e hijo."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (DIRECTORY / "parent.pid").write_text(str(os.getpid()), encoding="ascii")
    child = os.fork()
    if child == 0:
        os.setsid()
        (DIRECTORY / "child.pid").write_text(str(os.getpid()), encoding="ascii")
        (DIRECTORY / "child.session").write_text(str(os.getsid(0)), encoding="ascii")
    while True:
        signal.pause()


if __name__ == "__main__":
    main()
