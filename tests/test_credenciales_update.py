"""`scripts/update.sh` no actualiza nada con una contraseña de base de datos ausente o de ejemplo.

Se ejecuta el script real sobre un clon sintético, con un `docker` de pega que anota las órdenes. Antes del cambio,
con un `.env` inválido el script hacía el backup y traía el código, y era Compose quien paraba después.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    shutil.which("git") is None or shutil.which("curl") is None or shutil.which("gzip") is None,
    reason="requiere git, curl y gzip",
)

DOCKER_DE_PEGA = """#!/bin/sh
echo "docker $*" >> "$STUB_LOG"
exit 0
"""


def _preparar(tmp_path: Path, env_texto: str, modo: int = 0o600):
    raiz = tmp_path / "opt" / "zascarr"
    repo = raiz / "zascarr"
    (repo / "scripts").mkdir(parents=True)
    for f in ("docker-compose.yml", ".env.example"):
        shutil.copy(RAIZ / f, repo / f)
    for f in (RAIZ / "scripts").glob("*.sh"):
        shutil.copy(f, repo / "scripts" / f.name)
    (raiz / ".env").write_text(env_texto, encoding="utf-8")
    (raiz / ".env").chmod(modo)
    entorno = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "GIT_CONFIG_GLOBAL": "/dev/null"}
    for orden in (["init", "-q", "-b", "main"], ["add", "."], ["commit", "-q", "-m", "x"]):
        subprocess.run(["git", "-C", str(repo), *orden], check=True, capture_output=True, env=entorno)
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(DOCKER_DE_PEGA, encoding="utf-8")
    (bin_ / "docker").chmod(0o755)
    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8")
    return repo, raiz, bin_, log, entorno


def _update(repo: Path, bin_: Path, log: Path, entorno: dict, tmp_path: Path):
    return subprocess.run(
        ["bash", str(repo / "scripts" / "update.sh")], capture_output=True, text=True, timeout=120, check=False,
        env={**entorno, "PATH": f"{bin_}:{os.environ['PATH']}", "STUB_LOG": str(log),
             "BACKUP_DIR": str(tmp_path / "backups"), "HEALTH_TIMEOUT": "2"},
    )


@pytest.mark.parametrize("env_texto", [
    "TZ=UTC\n", "DB_PASSWORD=\n", "DB_PASSWORD=cambia_esto_ahora\n", "DB_PASSWORD=SuperSecretPassword123\n",
])
def test_update_se_detiene_antes_de_tocar_nada_con_una_contrasena_invalida(tmp_path, env_texto):
    repo, _, bin_, log, entorno = _preparar(tmp_path, env_texto)
    r = _update(repo, bin_, log, entorno, tmp_path)
    assert r.returncode != 0
    assert "NO se ha actualizado nada" in r.stderr
    assert "credenciales.sh" in r.stderr
    orden = log.read_text(encoding="utf-8")
    assert "pg_dump" not in orden and " build" not in orden and " up " not in orden
    refs = subprocess.run(["git", "-C", str(repo), "for-each-ref", "refs/zascarr"], capture_output=True, text=True)
    assert refs.stdout.strip() == "", "creó una referencia de rescate antes de comprobar la configuración"
    assert not (tmp_path / "backups").exists(), "hizo un backup antes de comprobar la configuración"


def test_update_con_una_contrasena_valida_pasa_la_comprobacion_y_llega_al_backup(tmp_path):
    sint = "Sint3tica-Update-0005"
    repo, _, bin_, log, entorno = _preparar(tmp_path, f"DB_PASSWORD={sint}\n")
    r = _update(repo, bin_, log, entorno, tmp_path)
    assert "NO se ha actualizado nada" not in r.stderr
    assert "pg_dump" in log.read_text(encoding="utf-8"), "no llegó al backup"
    assert sint not in r.stdout + r.stderr + log.read_text(encoding="utf-8")


def test_update_avisa_pero_no_falla_si_el_env_sigue_legible_por_otros(tmp_path):
    """Una instalación anterior lo dejó 644: se avisa con el arreglo, sin romper la actualización."""
    repo, _, bin_, log, entorno = _preparar(tmp_path, "DB_PASSWORD=Sint3tica-Update-0006\n", modo=0o644)
    r = _update(repo, bin_, log, entorno, tmp_path)
    salida = r.stdout + r.stderr
    assert "no está bien protegido" in salida and "credenciales.sh" in salida
    assert "pg_dump" in log.read_text(encoding="utf-8"), "el aviso no debe detener la actualización"
    assert "Sint3tica-Update-0006" not in salida
