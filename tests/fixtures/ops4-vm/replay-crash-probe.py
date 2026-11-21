"""Barreras de corte del registro: ejecutar solo en una VM desechable.

El controlador externo debe cortar QEMU al recibir CUT_READY. Este programa
no mata QEMU, no accede a la app ni reintenta una operación tras recuperarse.
"""
from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

DIRECTORY = Path("/var/lib/ops4-replay-cut")
ID = "a" * 32


def barrier(stage: int) -> None:
    """Anuncia la frontera y se detiene sin seguir a la próxima escritura."""
    print(f"CUT_READY:{stage}", flush=True)
    os.kill(os.getpid(), signal.SIGSTOP)
    raise RuntimeError("el sondeo no debe reanudarse tras la barrera")


def main() -> None:
    """Inyecta una barrera o comprueba el estado tras arrancar de nuevo."""
    from registro_repeticiones_ops4 import reclamar_id

    mode, stage_text = sys.argv[1:]
    stage = int(stage_text)
    if stage not in (1, 2, 3) or mode not in ("cut", "verify"):
        raise ValueError("caso de laboratorio no válido")
    if mode == "cut":
        DIRECTORY.mkdir(mode=0o700)
        # Acreditar la provisión del directorio antes de ensayar sus marcas.
        parent_fd = os.open(DIRECTORY.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    directory_fd = os.open(DIRECTORY, os.O_RDONLY | os.O_DIRECTORY)
    try:
        if mode == "cut":
            os.fsync(directory_fd)
        if mode == "verify":
            marker = DIRECTORY / f"solicitud-{ID}"
            exists = marker.exists()
            if stage == 3:
                assert exists, "se perdió una reclamación ya confirmada"
            if exists:
                assert reclamar_id(ID, directorio_fd=directory_fd) is False
            # Si el corte fue anterior a la confirmación, existencia y ausencia
            # son admisibles; no crear otra marca ni iniciar/reintentar nada.
            print(f"RECOVERED stage={stage} exists={exists} automatic_retry=False", flush=True)
            return
        calls = 0

        def sync(fd: int) -> None:
            nonlocal calls
            calls += 1
            if stage == calls:
                barrier(stage)
            os.fsync(fd)

        assert reclamar_id(ID, directorio_fd=directory_fd, sincronizar=sync) is True
        assert calls == 2
        assert stage == 3, "se atravesó una barrera sin cortar"
        barrier(3)
    finally:
        os.close(directory_fd)


if __name__ == "__main__":
    main()
