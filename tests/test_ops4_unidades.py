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


def _texto(nombre: str) -> str:
    return (UNIDADES / nombre).read_text(encoding="utf-8")


def test_unidad_de_actualizacion_tiene_accion_fija_y_limites() -> None:
    config = _leer("zascarr-actualizar.service")
    servicio = config["Service"]
    assert servicio["Type"] == "exec"
    assert servicio["ExecStart"] == (
        "/bin/bash @REPO@/scripts/update.sh --rama main"
    )
    assert servicio["RuntimeMaxSec"] == "5400"
    assert servicio["KillMode"] == "control-group"
    assert servicio["SendSIGKILL"] == "yes"
    assert servicio["Restart"] == "no"
    assert "/opt/zascarr" in servicio["ReadWritePaths"]
    assert servicio["WorkingDirectory"] == "@REPO@"
    assert "AF_INET" in servicio["RestrictAddressFamilies"]
    assert "Install" not in config


def test_la_unidad_no_marca_hecha_al_arrancar() -> None:
    """H-1/T-10: `ExecStartPost` escribía `hecha` tras el exec, no al terminar."""
    texto = _texto("zascarr-actualizar.service")
    lineas = [linea for linea in texto.splitlines() if linea.startswith("ExecStartPost=")]
    assert lineas == []


def test_unico_execstoppost_con_prefijo_y_mapeo_de_systemd() -> None:
    texto = _texto("zascarr-actualizar.service")
    stops = [linea for linea in texto.splitlines() if linea.startswith("ExecStopPost=")]
    assert len(stops) == 1
    assert stops[0].startswith("ExecStopPost=-")
    valor = stops[0][len("ExecStopPost="):]
    assert valor.startswith("-/bin/sh -c")
    for variable in ("SERVICE_RESULT", "EXIT_CODE", "EXIT_STATUS"):
        assert variable in valor
    # Tabla normativa de A1: solo el éxito limpio es `hecha`; el 75 del cerrojo
    # es pre-efecto por contrato; todo lo demás es incierta (H-13).
    assert 'success:exited:0) r=hecha' in valor
    assert 'exit-code:exited:75) r=fallida' in valor
    assert '*) r=incierta' in valor
    assert '--resultado "$r"' in valor


def test_readwritepaths_incluye_el_cerrojo_con_prefijo() -> None:
    servicio = _leer("zascarr-actualizar.service")["Service"]
    rutas = servicio["ReadWritePaths"].split()
    # H-7: un host sin OPS1 puede no tener /run/zascarr-ops.lock; el `-` evita
    # que el sandbox falle al arrancar la unidad.
    assert "-/run/zascarr-ops.lock" in rutas
    assert "/opt/zascarr" in rutas
    assert "/var/lib/zascarr" in rutas
    assert "/var/backups/zascarr" in rutas


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
