"""Instalador OPS4 en directorios temporales; no toca systemd ni la Pi."""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "instalar_actualizacion_ops4.sh"


def ejecutar(tmp_path: Path, *args: str, extra_env: dict | None = None,
             sin_grupo: bool = False):
    entorno = os.environ.copy()
    entorno.update({
        "ZASCARR_PRUEBAS": "1",
        "OPS4_DATA_DIR": str(tmp_path / "data"),
        "OPS4_DEST_AUX": str(tmp_path / "bin" / "actualizar-aux"),
        "OPS4_DEST_LIB": str(tmp_path / "lib"),
        "OPS4_DEST_UNIDADES": str(tmp_path / "units"),
        "OPS4_GROUP": subprocess.check_output(["id", "-gn"], text=True).strip(),
    })
    if sin_grupo:
        entorno.pop("OPS4_GROUP", None)
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
    assert (tmp_path / "lib" / "zascarr-estado-actualizar-ops4").is_file()
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
    unit_actualizar = (
        tmp_path / "units" / "zascarr-actualizar.service"
    ).read_text(encoding="utf-8")
    assert str(RAIZ) in unit_actualizar
    assert "@REPO@" not in unit_actualizar
    assert "systemd omitido" in r.stdout
    assert "OPS4_ACTUALIZACION_HABILITADA (por defecto false)" in r.stdout


def test_unidad_instalada_sustituye_grupo_sin_activar(tmp_path: Path) -> None:
    resultado = ejecutar(tmp_path, "--yes", "--sin-systemd")
    assert resultado.returncode == 0, resultado.stderr
    grupo = subprocess.check_output(["id", "-gn"], text=True).strip()
    unidad = (tmp_path / "units" / "zascarr-actualizar@.service").read_text(
        encoding="utf-8"
    )
    assert "User=root\n" in unidad
    assert f"Group={grupo}\n" in unidad
    assert "@GRUPO@" not in unidad
    assert "CapabilityBoundingSet=\n" in unidad
    assert "[Install]" not in unidad


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


def test_grupo_por_defecto_desde_env_pgid(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text(
        f"PGID={subprocess.check_output(['id', '-g'], text=True).strip()}\n",
        encoding="utf-8",
    )
    grupo = subprocess.check_output(["id", "-gn"], text=True).strip()
    r = ejecutar(
        tmp_path, "--yes", "--sin-systemd", sin_grupo=True,
        extra_env={"ENV_FILE": str(root / ".env"), "ZASCARR_ROOT": str(root)},
    )
    assert r.returncode == 0, r.stderr
    unit = tmp_path / "units" / "zascarr-actualizar.socket"
    assert f"SocketGroup={grupo}" in unit.read_text(encoding="utf-8")


def test_grupo_no_resuelto_aborta(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("PGID=424242\n", encoding="utf-8")
    r = ejecutar(
        tmp_path, "--yes", "--sin-systemd", sin_grupo=True,
        extra_env={"ENV_FILE": str(root / ".env"), "ZASCARR_ROOT": str(root)},
    )
    assert r.returncode == 1
    assert "No se pudo resolver el grupo" in r.stderr
    assert not (tmp_path / "data").exists()


def test_directorio_del_estado_queda_0750_para_el_grupo(tmp_path: Path) -> None:
    """H-5: la app corre con PUID:PGID; `ops` debe ser 0750 root:<grupo>."""
    r = ejecutar(tmp_path, "--yes", "--sin-systemd")
    assert r.returncode == 0, r.stderr
    ops = tmp_path / "data" / "ops"
    assert stat.S_IMODE(ops.stat().st_mode) == 0o750


def test_instalador_prepara_permisos_sin_habilitar() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    assert 'install -d -m 0750 "${OPS_DIR}"' in script
    assert 'chown "root:${GRUPO}" "${OPS_DIR}"' in script
    # Provisionar no es habilitar: solo --activar hace `systemctl start`.
    assert "systemctl enable" not in script.replace("systemctl disable", "")
    assert "systemctl start zascarr-actualizar.socket" in script
    assert "systemctl enable --now" not in script


def test_unidad_instalada_cierra_estado_sin_execstartpost(tmp_path: Path) -> None:
    r = ejecutar(tmp_path, "--yes", "--sin-systemd")
    assert r.returncode == 0, r.stderr
    texto = (tmp_path / "units" / "zascarr-actualizar.service").read_text(encoding="utf-8")
    assert "ExecStartPost=" not in texto
    stops = [linea for linea in texto.splitlines() if linea.startswith("ExecStopPost=")]
    assert len(stops) == 1
    assert stops[0].startswith("ExecStopPost=-")
    assert "-/run/zascarr-ops.lock" in texto
    assert str(tmp_path / "data") in texto
    assert "@ZASCARR_DATA_DIR@" not in texto
