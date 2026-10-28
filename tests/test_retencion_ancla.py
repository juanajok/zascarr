"""Retención por referencia viva (#334): un dump con ref no se borra por edad.

La regla es la que pidió el responsable: si existe `refs/zascarr/update/<TS>` o
`refs/zascarr/rollback-rescue/<TS>`, su dump sobrevive; el resto de dumps caduca
a los RETENTION_DAYS. Se prueba también la poda de una ref sin dump.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"

RUN_SH = """set -euo pipefail
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:?}"
RETENTION_DAYS=14
source "$(dirname "$0")/_comun.sh"
aplicar_retencion "${1:-}"
if [[ "${2:-}" == "--prune" ]]; then
    podar_refs_huerfanas
fi
"""

NOMBRES = (
    "update_20261001_000000.sql.gz",
    "update_20261002_000000.sql.gz",
    "update_20261004_000000.sql.gz",
    "rollback-safety_20261003_000000.sql.gz",
    "rollback-safety_20261005_000000.sql.gz",
    "backup_20261006_000000.sql.gz",
)
VIVOS = {
    "update_20261001_000000.sql.gz",
    "update_20261002_000000.sql.gz",
    "rollback-safety_20261003_000000.sql.gz",
}


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _preparar(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("_comun.sh", "_credenciales.sh"):
        shutil.copy2(SCRIPTS / nombre, repo / "scripts" / nombre)
    (repo / "scripts" / "run.sh").write_text(RUN_SH, encoding="utf-8")
    (repo / "README").write_text("", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")
    sha = _git(repo, "rev-parse", "HEAD").stdout.strip()

    _git(repo, "update-ref", "refs/zascarr/update/20261001_000000", sha)
    _git(repo, "update-ref", "refs/zascarr/update/20261002_000000", sha)
    _git(repo, "update-ref", "refs/zascarr/rollback-rescue/20261003_000000", sha)
    # Ref sin dump: debe podarse al final.
    _git(repo, "update-ref", "refs/zascarr/update/20261007_000000", sha)

    backup = tmp_path / "backup"
    backup.mkdir()
    for nombre in NOMBRES:
        (backup / nombre).write_text("", encoding="utf-8")
    _envejecer(backup)

    return {"repo": repo, "backup": backup}


def _envejecer(directorio: Path) -> None:
    viejo = time.time() - 20 * 24 * 3600
    for ruta in directorio.iterdir():
        if ruta.is_file():
            os.utime(ruta, (viejo, viejo))


def _ejecutar(ctx: dict, directorio: Path, *args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["BACKUP_DIR"] = str(ctx["backup"])
    return subprocess.run(
        ["bash", str(ctx["repo"] / "scripts" / "run.sh"), str(directorio), *args],
        env=env, capture_output=True, text=True, timeout=60,
    )


class TestRetencionPorRef:

    def test_protege_los_dumps_con_ref_y_borra_el_resto(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, ctx["backup"])
        assert r.returncode == 0, r.stdout + r.stderr

        quedan = {p.name for p in ctx["backup"].iterdir()}
        assert quedan >= VIVOS
        assert "update_20261004_000000.sql.gz" not in quedan
        assert "rollback-safety_20261005_000000.sql.gz" not in quedan
        assert "backup_20261006_000000.sql.gz" not in quedan

    def test_la_misma_regla_se_aplica_al_offsite(self, tmp_path):
        ctx = _preparar(tmp_path)
        offsite = tmp_path / "offsite"
        offsite.mkdir()
        for nombre in NOMBRES:
            (offsite / nombre).write_text("", encoding="utf-8")
        _envejecer(offsite)

        r = _ejecutar(ctx, offsite)
        assert r.returncode == 0, r.stdout + r.stderr

        quedan = {p.name for p in offsite.iterdir()}
        assert quedan >= VIVOS
        assert "update_20261004_000000.sql.gz" not in quedan
        assert "backup_20261006_000000.sql.gz" not in quedan

    def test_poda_la_ref_sin_dump_y_conserva_las_vivas(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, ctx["backup"], "--prune")
        assert r.returncode == 0, r.stdout + r.stderr

        refs = _git(
            ctx["repo"], "for-each-ref", "refs/zascarr/update", "--format=%(refname)"
        ).stdout
        assert "20261007_000000" not in refs
        assert "20261001_000000" in refs
        assert "20261002_000000" in refs
