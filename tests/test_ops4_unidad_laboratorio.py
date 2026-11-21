"""Contrato inerte de los fixtures systemd; pytest no instala ni arranca unidades."""
from __future__ import annotations

import configparser
import os
import runpy
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "ops4-vm"
ROOT = Path(__file__).resolve().parents[1]


def test_unidad_sintetica_acota_cgroup_sin_reinicio() -> None:
    config = configparser.ConfigParser(interpolation=None)
    config.read(FIXTURES / "ops4-lab-timeout.service")
    service = config["Service"]
    # RuntimeMaxSec no limita Type=oneshot: este sondeo debe usar Type=exec.
    assert service["Type"] == "exec"
    assert service["RuntimeMaxSec"] == "2s"
    assert service["TimeoutStopSec"] == "1s"
    assert service["KillMode"] == "control-group"
    assert service["SendSIGKILL"] == "yes"
    assert service["Restart"] == "no"
    assert service["User"] == "nobody"
    assert service["CapabilityBoundingSet"] == ""
    assert service["ExecStart"] == (
        "/usr/bin/python3 /usr/local/lib/ops4-lab/timeout-probe.py"
    )
    assert "Install" not in config


def test_importar_fixtures_no_lanza_procesos(monkeypatch) -> None:
    def prohibido(*_args, **_kwargs):
        raise AssertionError("el fixture no debe ejecutarse al importarlo")

    monkeypatch.setattr(os, "fork", prohibido)
    monkeypatch.setattr(subprocess, "run", prohibido)
    monkeypatch.setattr(subprocess, "check_output", prohibido)
    for name in ("timeout-probe.py", "verify-timeout.py", "replay-crash-probe.py"):
        runpy.run_path(str(FIXTURES / name), run_name="fixture_inspection")


def test_instalador_no_incluye_unidad_de_laboratorio() -> None:
    installer = (ROOT / "scripts" / "instalar_ops.sh").read_text(encoding="utf-8")
    assert "ops4-lab-timeout" not in installer
    assert "timeout-probe.py" not in installer
