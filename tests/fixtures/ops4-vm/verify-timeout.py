"""Verifica el sondeo instalado solo en la VM desechable, como root.

No se ejecuta al importar, ni como parte automática de pytest. No instala
unidades: exige que el controlador de laboratorio haya copiado los fixtures.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

UNIT = "ops4-lab-timeout.service"
DIRECTORY = Path("/run/ops4-lab-timeout")


def main() -> None:
    """Exige timeout, cero reinicios y ningún proceso sintético activo."""
    env = {
        "PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
        "SYSTEMD_PAGER": "cat",
        "DBUS_SYSTEM_BUS_ADDRESS": "unix:path=/run/systemd/private",
    }
    subprocess.run(["systemctl", "daemon-reload"], env=env, check=True, timeout=15)
    # --wait requiere operaciones del bus que el socket privado no soporta.
    # Arrancar y observar con plazo externo, sin confundir start=0 con éxito.
    subprocess.run(["systemctl", "start", UNIT], env=env, check=True, timeout=15)
    deadline = time.monotonic() + 15
    while True:
        properties = subprocess.check_output(
            ["systemctl", "show", UNIT, "-p", "Result", "-p", "ExecMainStatus",
             "-p", "ActiveState", "-p", "SubState", "-p", "NRestarts"],
            env=env, timeout=5, text=True,
        )
        values = dict(line.split("=", 1) for line in properties.splitlines() if "=" in line)
        if values.get("ActiveState") == "failed":
            break
        if time.monotonic() >= deadline:
            raise AssertionError("la unidad no terminó por timeout: " + properties)
        time.sleep(0.1)
    assert values["Result"] == "timeout", properties
    assert values["ExecMainStatus"] == "9", properties
    assert values["ActiveState"] == "failed", properties
    assert values["SubState"] == "failed", properties
    assert values["NRestarts"] == "0", properties
    parent = int((DIRECTORY / "parent.pid").read_text(encoding="ascii"))
    child = int((DIRECTORY / "child.pid").read_text(encoding="ascii"))
    session = int((DIRECTORY / "child.session").read_text(encoding="ascii"))
    assert child == session, "el hijo no llegó a cambiar de sesión"
    assert os.getpid() not in (parent, child), "el sondeo no es el verificador"
    for pid in (parent, child):
        try:
            stat = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        except FileNotFoundError:
            continue
        state = stat.rsplit(")", 1)[1].split()[0]
        assert state in ("Z", "X"), f"proceso sintético activo: {pid} ({state})"
    print(properties, end="")
    print("PASS timeout, padre e hijo en otra sesión detenidos, cero reinicios")


if __name__ == "__main__":
    main()
