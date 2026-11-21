"""Contrato estático de las unidades OPS4; no instala ni arranca systemd."""
from __future__ import annotations

import configparser
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UNIDADES = RAIZ / "deploy" / "systemd"


def _leer(nombre: str) -> configparser.ConfigParser:
    config = configparser.ConfigParser(interpolation=None, strict=False)
    config.read(UNIDADES / nombre)
    return config


def test_unidad_de_actualizacion_tiene_accion_fija_y_limites() -> None:
    config = _leer("zascarr-actualizar.service")
    servicio = config["Service"]
    assert servicio["Type"] == "exec"
    assert servicio["ExecStart"] == (
        "/bin/bash /opt/zascarr/zascarr/scripts/update.sh --rama main"
    )
    assert servicio["RuntimeMaxSec"] == "5400"
    assert servicio["KillMode"] == "control-group"
    assert servicio["SendSIGKILL"] == "yes"
    assert servicio["Restart"] == "no"
    assert "/opt/zascarr" in servicio["ReadWritePaths"]
    assert "AF_INET" in servicio["RestrictAddressFamilies"]
    assert "Install" not in config


def test_unidad_auxiliar_no_tiene_red_ni_capacidades() -> None:
    config = _leer("zascarr-actualizar@.service")
    servicio = config["Service"]
    assert servicio["StandardInput"] == "socket"
    assert servicio["ExecStart"].endswith("/usr/local/lib/zascarr/zascarr-actualizar-aux")
    assert servicio["PrivateNetwork"] == "yes"
    assert servicio["RestrictAddressFamilies"] == "AF_UNIX"
    assert servicio["CapabilityBoundingSet"] == ""
    assert servicio["RuntimeMaxSec"] == "45s"
    assert "ReadWritePaths" in servicio


def test_socket_es_propio_y_no_se_instala_solo() -> None:
    config = _leer("zascarr-actualizar.socket")
    socket = config["Socket"]
    assert socket["ListenStream"] == "@ZASCARR_DATA_DIR@/ops/actualizar.sock"
    assert socket["Accept"] == "yes"
    assert socket["SocketMode"] == "0660"
    assert "Install" not in config


def test_el_instalador_actual_no_instala_ops4() -> None:
    texto = (RAIZ / "scripts" / "instalar_ops.sh").read_text(encoding="utf-8")
    for nombre in (
        "zascarr-actualizar.socket", "zascarr-actualizar.service",
        "zascarr-actualizar@.service", "actualizar.key",
    ):
        assert nombre not in texto
