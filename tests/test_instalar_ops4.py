"""Instalador OPS4 en directorios temporales; no toca systemd ni la Pi."""
from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "instalar_actualizacion_ops4.sh"


def ejecutar(tmp_path: Path, *args: str, extra_env: dict | None = None):
    entorno = os.environ.copy()
    entorno.update({
        "ZASCARR_PRUEBAS": "1",
        "OPS4_DATA_DIR": str(tmp_path / "data"),
        "OPS4_DEST_AUX": str(tmp_path / "bin" / "actualizar-aux"),
        "OPS4_DEST_LIB": str(tmp_path / "lib"),
        "OPS4_DEST_UNIDADES": str(tmp_path / "units"),
        "OPS4_GROUP": subprocess.check_output(["id", "-gn"], text=True).strip(),
    })
    if extra_env:
        entorno.update(extra_env)
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=entorno, capture_output=True,
        text=True, timeout=60,
    )


def test_instala_clave_dirs_modulos_y_unidades_sin_activar(tmp_path: Path) -> None:
    r = ejecutar(tmp_path, "--yes", "--sin-systemd")
    assert r.returncode == 0, r.stderr
    key = tmp_path / "data" / "ops" / "actualizar.key"
    assert key.exists() and key.stat().st_size == 65
    assert key.stat().st_mode & 0o777 == 0o440
    assert (tmp_path / "data" / "ops4" / "consumidos").is_dir()
    assert (tmp_path / "bin" / "actualizar-aux").is_file()
    for modulo in ("protocolo_actualizar_v4_ops4.py",
                   "verificador_autorizacion_ops4.py",
                   "registro_repeticiones_ops4.py"):
        assert (tmp_path / "lib" / modulo).is_file()
    for unidad in ("zascarr-actualizar.socket", "zascarr-actualizar@.service",
                   "zascarr-actualizar.service"):
        destino = tmp_path / "units" / unidad
        assert destino.is_file()
        texto = destino.read_text(encoding="utf-8")
        if unidad != "zascarr-actualizar.service":
            assert str(tmp_path / "data") in texto
    assert "/opt/zascarr/zascarr" in (
        tmp_path / "units" / "zascarr-actualizar.service"
    ).read_text(encoding="utf-8")
    assert "systemd omitido" in r.stdout
    assert "OPS4_ACTUALIZACION_HABILITADA=false" in r.stdout


def test_idempotente_conserva_la_clave(tmp_path: Path) -> None:
    assert ejecutar(tmp_path, "--yes", "--sin-systemd").returncode == 0
    key = tmp_path / "data" / "ops" / "actualizar.key"
    antes = hashlib.sha256(key.read_bytes()).hexdigest()
    r = ejecutar(tmp_path, "--yes", "--sin-systemd")
    assert r.returncode == 0
    assert hashlib.sha256(key.read_bytes()).hexdigest() == antes
    assert "Clave existente" in r.stdout


def test_dry_run_no_escribe(tmp_path: Path) -> None:
    r = ejecutar(tmp_path, "--dry-run")
    assert r.returncode == 0
    assert not (tmp_path / "data").exists()
    assert not (tmp_path / "units").exists()
    assert "dry-run" in r.stdout


def test_quitar_conserva_clave_y_borrar_clave_la_elimina(tmp_path: Path) -> None:
    assert ejecutar(tmp_path, "--yes", "--sin-systemd").returncode == 0
    key = tmp_path / "data" / "ops" / "actualizar.key"
    assert ejecutar(tmp_path, "--quitar", "--sin-systemd").returncode == 0
    assert key.exists()
    assert not (tmp_path / "units" / "zascarr-actualizar.socket").exists()
    assert ejecutar(
        tmp_path, "--quitar", "--sin-systemd", "--borrar-clave",
    ).returncode == 0
    assert not key.exists()


@pytest.mark.parametrize("args", [("--opcion-mala",), ("--borrar-clave",)])
def test_argumentos_invalidos(tmp_path: Path, args) -> None:
    assert ejecutar(tmp_path, *args).returncode == 2
