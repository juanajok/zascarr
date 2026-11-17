"""BL-OPS1 FR-26/27 (AC-25, AC-28): `instalar_ops.sh` sin systemd, con herramientas falsas y destinos temporales."""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "instalar_ops.sh"
HERRAMIENTAS = ("bash", "sed", "tr", "cut", "cat", "cmp", "mktemp", "rm", "mv", "mkdir", "chmod", "id", "dirname",
                "tail", "getent", "env", "umask", "head", "date", "docker")


@pytest.fixture()
def entorno(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for h in HERRAMIENTAS:
        ruta = shutil.which(h)
        if ruta:
            (bin_ / h).symlink_to(ruta)
    registro = tmp_path / "llamadas.log"
    for falso in ("systemctl", "systemd-tmpfiles", "chown"):
        f = bin_ / falso
        f.write_text(f'#!/bin/bash\necho "{falso} $*" >> "{registro}"\n')
        f.chmod(0o755)
    # `install` real pero sin -o/-g (no somos root)
    real = shutil.which("install")
    f = bin_ / "install"
    f.write_text('#!/bin/bash\nargs=()\nwhile (($#)); do case "$1" in -o|-g) shift 2;; *) args+=("$1"); shift;; esac; done\n'
                 f'exec {real} "${{args[@]}}"\n')
    f.chmod(0o755)
    python = shutil.which("python3")
    (bin_ / "python3").symlink_to(python)
    datos = tmp_path / "datos"
    env = {
        "PATH": str(bin_), "HOME": str(tmp_path), "ZASCARR_PRUEBAS": "1", "ZASCARR_DATA_DIR": str(datos),
        "OPS_GROUP": subprocess.run(["id", "-gn"], capture_output=True, text=True).stdout.strip(),
        "ENV_FILE": str(tmp_path / "no.env"),
        "OPS_DEST_AUXILIAR": str(tmp_path / "lib" / "zascarr-ops"),
        "OPS_DEST_UNIDADES": str(tmp_path / "units"), "OPS_DEST_TMPFILES": str(tmp_path / "tmpfiles" / "z.conf"),
    }
    return {"env": env, "datos": datos, "bin": bin_, "registro": registro, "tmp": tmp_path}


def _correr(e, *args, env_extra=None):
    env = dict(e["env"], **(env_extra or {}))
    return subprocess.run(["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, timeout=60)


def _llamadas(e) -> list[str]:
    return e["registro"].read_text().splitlines() if e["registro"].exists() else []


def test_instala_y_la_clave_son_64_hex_con_modo_0440_y_no_sale_por_pantalla(entorno):
    r = _correr(entorno, "--yes")
    assert r.returncode == 0, r.stderr
    clave = (entorno["datos"] / "ops" / "ops.key")
    texto = clave.read_text().strip()
    assert re.fullmatch(r"[0-9a-f]{64}", texto)
    assert stat.S_IMODE(clave.stat().st_mode) == 0o440
    assert texto not in r.stdout + r.stderr
    assert (entorno["tmp"] / "lib" / "zascarr-ops").stat().st_mode & 0o777 == 0o755
    socket_ = (entorno["tmp"] / "units" / "zascarr-ops.socket").read_text()
    assert str(entorno["datos"]) in socket_ and "@" not in socket_       # sin marcadores sin sustituir
    assert "enable --now zascarr-ops.socket" in " ".join(_llamadas(entorno))
    assert any(x.startswith("systemd-tmpfiles --create") for x in _llamadas(entorno))


def test_segunda_ejecucion_no_cambia_clave_ni_duplica(entorno):
    _correr(entorno, "--yes")
    clave = entorno["datos"] / "ops" / "ops.key"
    antes = clave.read_text()
    huella = sorted(p.name for p in entorno["tmp"].rglob("*") if "bin" not in p.parts and p.is_file())
    r = _correr(entorno, "--yes")
    assert r.returncode == 0 and "Sin cambios" in r.stdout
    assert clave.read_text() == antes
    assert sorted(p.name for p in entorno["tmp"].rglob("*") if "bin" not in p.parts and p.is_file()
                  if p.name != "llamadas.log") == [h for h in huella if h != "llamadas.log"]


def test_dry_run_no_escribe_nada(entorno):
    r = _correr(entorno, "--dry-run")
    assert r.returncode == 0
    assert not entorno["datos"].exists()
    assert not (entorno["tmp"] / "units").exists() and not (entorno["tmp"] / "lib").exists()
    assert _llamadas(entorno) == []


def test_sin_python3_aborta_antes_de_crear_nada(entorno):
    (entorno["bin"] / "python3").unlink()
    r = _correr(entorno, "--yes")
    assert r.returncode == 1 and "python3" in r.stderr
    assert not entorno["datos"].exists() and not (entorno["tmp"] / "units").exists()


def test_sin_grupo_aborta_antes_de_crear_nada(entorno):
    r = _correr(entorno, "--yes", env_extra={"OPS_GROUP": "grupo-que-no-existe-zz"})
    assert r.returncode == 1 and "grupo" in r.stderr
    assert not entorno["datos"].exists()


def test_refrescar_sin_instalar_solo_informa(entorno):
    r = _correr(entorno, "--refrescar")
    assert r.returncode == 0 and "instalar_ops.sh" in r.stdout
    assert not entorno["datos"].exists() and _llamadas(entorno) == []


def test_refrescar_instalado_sin_cambios_no_reinicia_y_con_cambios_si(entorno):
    _correr(entorno, "--yes")
    entorno["registro"].unlink()
    r = _correr(entorno, "--refrescar")
    assert r.returncode == 0 and "Sin cambios" in r.stdout
    assert not any("restart" in x for x in _llamadas(entorno))
    (entorno["tmp"] / "lib" / "zascarr-ops").write_text("viejo")          # el instalado ya no coincide
    r = _correr(entorno, "--refrescar")
    assert "restart zascarr-ops.socket" in " ".join(_llamadas(entorno))
    assert (entorno["tmp"] / "lib" / "zascarr-ops").read_text() == (REPO / "deploy/ops/zascarr_ops.py").read_text()


def test_quitar_conserva_la_clave_salvo_borrar_clave(entorno):
    _correr(entorno, "--yes")
    clave = entorno["datos"] / "ops" / "ops.key"
    r = _correr(entorno, "--quitar")
    assert r.returncode == 0 and clave.exists()
    assert not (entorno["tmp"] / "units" / "zascarr-ops.socket").exists()
    _correr(entorno, "--quitar", "--borrar-clave")
    assert not clave.exists()


def test_borrar_clave_sin_quitar_se_rechaza(entorno):
    assert _correr(entorno, "--borrar-clave").returncode == 2


def test_las_unidades_cumplen_fr29_y_fr01():
    servicio = (REPO / "deploy/systemd/zascarr-ops@.service").read_text()
    for linea in ("StandardInput=socket", "StandardOutput=socket", "StandardError=journal", "NoNewPrivileges=yes",
                  "ProtectSystem=strict", "ProtectHome=yes", "PrivateTmp=yes", "PrivateNetwork=yes",
                  "RestrictAddressFamilies=AF_UNIX", "MemoryMax=64M", "TimeoutStartSec=15s"):
        assert linea in servicio.splitlines(), linea
    assert "ReadWritePaths=@BACKUP_STATUS_DIR@ /run/zascarr-ops" in servicio
    sock = (REPO / "deploy/systemd/zascarr-ops.socket").read_text().splitlines()
    for linea in ("Accept=yes", "SocketUser=root", "SocketGroup=@GRUPO@", "SocketMode=0660", "MaxConnections=4"):
        assert linea in sock, linea
    assert ((REPO / "deploy/systemd/zascarr-ops.tmpfiles.conf").read_text().strip()
            == "d /run/zascarr-ops 0700 root root -\nd /run/zascarr-ops/docker 0700 root root -"
               "\nf /run/zascarr-ops.lock 0600 root root -")
    assert os.access(SCRIPT, os.R_OK)


def test_la_carpeta_del_canal_es_0750(entorno):
    _correr(entorno, "--yes")
    assert stat.S_IMODE((entorno["datos"] / "ops").stat().st_mode) == 0o750


def test_sin_systemctl_aborta_antes_de_crear_nada(entorno):
    (entorno["bin"] / "systemctl").unlink()
    r = _correr(entorno, "--yes")
    assert r.returncode == 1 and "systemctl" in r.stderr
    assert not entorno["datos"].exists() and not (entorno["tmp"] / "units").exists()


def test_python_viejo_aborta_antes_de_crear_nada(entorno):
    (entorno["bin"] / "python3").unlink()
    falso = entorno["bin"] / "python3"
    falso.write_text("#!/bin/bash\nexit 1\n")
    falso.chmod(0o755)
    r = _correr(entorno, "--yes")
    assert r.returncode == 1 and "3.9" in r.stderr and not entorno["datos"].exists()


def test_sin_root_y_sin_pruebas_pide_sudo_y_no_escribe(entorno):
    env_extra = {"ZASCARR_PRUEBAS": ""}
    r = _correr(entorno, "--yes", env_extra=env_extra)
    if os.geteuid() != 0:
        assert r.returncode == 1 and "sudo" in r.stderr
    assert not (entorno["tmp"] / "units").exists() and not (entorno["tmp"] / "lib").exists()


def test_los_destinos_de_pruebas_no_valen_sin_zascarr_pruebas(entorno):
    """El override de destinos solo existe con ZASCARR_PRUEBAS=1; sin él, `--dry-run` muestra los fijos."""
    r = _correr(entorno, "--dry-run", env_extra={"ZASCARR_PRUEBAS": ""})
    assert "/usr/local/lib/zascarr/zascarr-ops" in r.stdout and str(entorno["tmp"] / "lib") not in r.stdout
    assert "/etc/systemd/system/zascarr-ops.socket" in r.stdout


def test_una_clave_que_aparece_durante_la_instalacion_no_se_pisa(entorno):
    """`mv -n`: si otra ejecución creó la clave entre la comprobación y el `mv`, no se sobrescribe."""
    texto = SCRIPT.read_text()
    assert "mv -n" in texto and "mv -f" not in texto


def test_restaurar_tiene_entorno_y_cerrojo_escribible():
    """B-1/B-2 de SecOps: el wrapper exporta lo que exige el script y la unidad puede crear el cerrojo."""
    unidad = (REPO / "deploy/systemd/zascarr-restaurar@.service").read_text()
    envoltorio = (REPO / "deploy/ops/restaurar-produccion.sh").read_text()
    for var in ("REPO_DIR", "ENV_FILE", "COMPOSE_FILE", "DB_NAME", "DB_USER"):
        assert f"export {var}=" in envoltorio
    assert "Environment=ZASCARR_REPO=" not in unidad
    assert "ReadWritePaths=/run/zascarr-ops.lock" in unidad
    assert "f /run/zascarr-ops.lock 0600 root root -" in (
        REPO / "deploy/systemd/zascarr-ops.tmpfiles.conf").read_text()
    assert '=~ ^[0-9]{8}_[0-9]{6}$' in envoltorio
    # QA en la VM: con ProtectHome=true el cliente docker necesita un DOCKER_CONFIG de root dentro de /run, y
    # la app real escucha en el 8000 (el 18000 solo era del arnés).
    assert "export DOCKER_CONFIG=" in envoltorio and "/run/zascarr-ops/docker" in envoltorio
    assert "HEALTH_URL" in envoltorio and "127.0.0.1:8000" in envoltorio
    assert "DOCKER_CONFIG=/run/zascarr-ops/docker" in unidad
    assert "HEALTH_URL=http://127.0.0.1:8000/api/health" in unidad


def test_la_unidad_de_restauracion_no_deja_marcadores_y_escribe_en_la_carpeta_de_copias(entorno):
    """F-16/QA: sin `BACKUP_DIR` definido, `@BACKUP_DIR@` quedaba sin sustituir (o vacío) y con
    `ProtectSystem=strict` el script no podía escribir en la carpeta de copias."""
    import re

    r = _correr(entorno, "--yes")
    assert r.returncode == 0, r.stderr
    unidad = (entorno["tmp"] / "units" / "zascarr-restaurar@.service").read_text()
    assert "@BACKUP_DIR@" not in unidad and "@BACKUP_STATUS_DIR@" not in unidad
    assert not re.search(r"@[A-Z_]+@", unidad), unidad          # ningún marcador sin sustituir
    assert "ProtectSystem=strict" in unidad
    assert f"{entorno['datos']}/backup-status" in unidad
    assert "/var/backups/zascarr/postgres" in unidad            # valor por defecto de _comun.sh/instalar_backup.sh
    readwrite = next(linea for linea in unidad.splitlines() if linea.startswith("ReadWritePaths="))
    assert "/var/backups/zascarr/postgres" in readwrite
    assert "/opt/zascarr" not in readwrite                               # no se escribe código de la app
    # F-16: endurecimiento de la unidad de restauración (el mismo conjunto que el auxiliar donde aplica).
    for linea in ("Requires=docker.service", "NoNewPrivileges=true", "ProtectSystem=strict", "ProtectHome=true",
                  "PrivateTmp=true", "ProtectKernelTunables=true", "ProtectKernelModules=true",
                  "ProtectControlGroups=true", "PrivateDevices=true", "RestrictNamespaces=true",
                  "RestrictSUIDSGID=true", "UMask=0077", "CapabilityBoundingSet=", "SuccessExitStatus=75"):
        assert linea in unidad.splitlines(), linea
    assert "TimeoutStartSec=2700" in unidad                              # 45 min (FR-26)
    assert "RuntimeMaxSec=" not in unidad                                # no mata una recuperación a mitad


def test_backup_dir_del_env_se_usa_en_la_unidad_de_restauracion(entorno):
    """Si `/etc/default/zascarr` (o el entorno) fija `BACKUP_DIR`, la unidad debe escribir ahí y no en el fijo."""
    env_file = entorno["tmp"] / "zascarr.env"
    env_file.write_text("BACKUP_DIR=/srv/copias-zascarr\n", encoding="utf-8")
    r = _correr(entorno, "--yes", env_extra={"ENV_FILE": str(env_file)})
    assert r.returncode == 0, r.stderr
    unidad = (entorno["tmp"] / "units" / "zascarr-restaurar@.service").read_text()
    readwrite = next(linea for linea in unidad.splitlines() if linea.startswith("ReadWritePaths="))
    assert "/srv/copias-zascarr" in readwrite
    assert "/var/backups/zascarr/postgres" not in readwrite
    assert "@BACKUP_DIR@" not in unidad
