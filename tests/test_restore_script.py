"""Pruebas de scripts/probar_restauracion.sh (#334 B2) con un `docker` falso.

No necesitan PostgreSQL real: el script se ejecuta tal cual, con un `docker` de
mentira que responde a createdb/dropdb/psql. Cubren el éxito, el dump truncado,
el recuento distinto, el fallo de psql, la base temporal siempre borrada, la app
sin arrancar y el aviso cuando el manifiesto falta o no acredita el commit.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"

DOCKER_FALSO = r"""#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  *"compose version"*) echo "Docker Compose version v2"; exit 0 ;;
  *"createdb"*) echo "createdb $*" >> "$DB_LOG"; exit 0 ;;
  *"dropdb"*) echo "dropdb $*" >> "$DB_LOG"; exit 0 ;;
  *"psql"*)
    if [[ "$*" == *" -c "* ]]; then
      case "$*" in
        *"information_schema.tables"*) echo "${FAKE_TABLES:-28}" ;;
        *"to_regclass"*) echo "t" ;;
        *"version_num"*) echo "${FAKE_ALEMBIC:-0020}" ;;
        *"count(*) from files"*) echo "${FAKE_FILES:-3}" ;;
        *"count(*) from series"*) echo "${FAKE_SERIES:-2}" ;;
        *"count(*) from issues"*) echo "${FAKE_ISSUES:-1}" ;;
        *"count(*) from wishlist"*) echo "${FAKE_WISHLIST:-0}" ;;
        *) echo "" ;;
      esac
      exit 0
    fi
    if [[ "${FAKE_PSQL_FAIL:-0}" == "1" ]]; then echo "boom" >&2; exit 1; fi
    cat > "$RESTORE_LOG"
    exit 0 ;;
esac
exit 0
"""


def _sql_fixture() -> str:
    tablas = ["alembic_version", "files", "series", "issues", "wishlist"]
    tablas += [f"tabla_{i:02d}" for i in range(23)]
    lineas = ["--", "-- PostgreSQL database dump", "--"]
    lineas += [f"CREATE TABLE public.{t} (id integer);" for t in tablas]
    lineas += ["COPY public.alembic_version (version_num) FROM stdin;", "0020", "\\."]
    lineas += ["COPY public.files (id) FROM stdin;", "1", "2", "3", "\\."]
    lineas += ["COPY public.series (id) FROM stdin;", "1", "2", "\\."]
    lineas += ["COPY public.issues (id) FROM stdin;", "1", "\\."]
    lineas += ["COPY public.wishlist (id) FROM stdin;", "\\."]
    return "\n".join(lineas) + "\n"


def _preparar(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("probar_restauracion.sh", "_comun.sh", "_credenciales.sh"):
        shutil.copy2(SCRIPTS / nombre, repo / "scripts" / nombre)
    (repo / "docker-compose.yml").write_text("", encoding="utf-8")

    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("DB_PASSWORD=test\n", encoding="utf-8")

    backup = tmp_path / "backup"
    offsite = tmp_path / "offsite"
    status = tmp_path / "status"
    for d in (backup, offsite, status):
        d.mkdir()

    dump = backup / "backup_20261028_120000.sql.gz"
    dump.write_bytes(gzip.compress(_sql_fixture().encode("utf-8")))
    sha = hashlib.sha256(dump.read_bytes()).hexdigest()
    bytes_ = dump.stat().st_size
    manifest = backup / "MANIFIESTO-backup_20261028_120000.json"
    manifest.write_text(json.dumps({
        "backup": dump.name, "sha256": sha, "bytes": bytes_,
        "alembic": "0020",
        "codigo_destino_sha_completo": "a" * 40,
        "codigo_desplegado_sha_completo": "b" * 40,
    }), encoding="utf-8")
    (backup / f"{dump.name}.sha256").write_text(f"{sha}  {dump.name}\n", encoding="utf-8")

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    docker = bin_ / "docker"
    docker.write_text(DOCKER_FALSO, encoding="utf-8")
    docker.chmod(0o755)
    stub = tmp_path / "docker.log"
    stub.write_text("", encoding="utf-8")
    db = tmp_path / "db.log"
    db.write_text("", encoding="utf-8")
    restore = tmp_path / "restore.log"
    restore.write_text("", encoding="utf-8")

    return {
        "repo": repo, "root": root, "backup": backup, "offsite": offsite,
        "status": status, "dump": dump, "manifest": manifest, "bin": bin_,
        "stub": stub, "db": db, "restore": restore,
    }


def _ejecutar(ctx: dict, *, dump: Path | None = None, manifest: Path | None = None,
              extra_env: dict | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update({
        "PATH": f"{ctx['bin']}:{env['PATH']}",
        "ZASCARR_REPO": str(ctx["repo"]),
        "ZASCARR_ROOT": str(ctx["root"]),
        "BACKUP_DIR": str(ctx["backup"]),
        "BACKUP_OFFSITE_DIR": str(ctx["offsite"]),
        "BACKUP_STATUS_DIR": str(ctx["status"]),
        "RESTORE_STATUS_FILE": str(ctx["status"] / "restore-status.json"),
        "STUB_LOG": str(ctx["stub"]),
        "DB_LOG": str(ctx["db"]),
        "RESTORE_LOG": str(ctx["restore"]),
    })
    if extra_env:
        env.update(extra_env)
    args = ["bash", str(ctx["repo"] / "scripts" / "probar_restauracion.sh")]
    if dump is not None:
        args += ["--dump", str(dump)]
    if manifest is not None:
        args += ["--manifest", str(manifest)]
    return subprocess.run(
        args, env=env, capture_output=True, text=True, timeout=60,
        stdin=subprocess.DEVNULL,
    )


def _estado(ctx: dict) -> dict:
    return json.loads((ctx["status"] / "restore-status.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")
class TestRestoreScript:

    def test_restaura_y_comprueba_recuentos(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode == 0, r.stdout + r.stderr

        estado = _estado(ctx)
        assert estado["status"] == "ok"
        assert estado["error"] is None
        assert estado["tablas"] == 28
        assert estado["alembic"] == "0020"
        assert estado["recuentos"] == {"files": 3, "series": 2, "issues": 1, "wishlist": 0}
        assert estado["codigo_destino"] == "a" * 40
        assert estado["codigo_desplegado"] == "b" * 40

        db = ctx["db"].read_text(encoding="utf-8")
        assert "createdb" in db and "dropdb" in db
        assert "zascarr_restore_" in db
        stub = ctx["stub"].read_text(encoding="utf-8")
        assert "zascarr" not in stub.replace("zascarr_restore_", "")
        assert ctx["restore"].read_text(encoding="utf-8")

    def test_dump_truncado_no_crea_base(self, tmp_path):
        ctx = _preparar(tmp_path)
        ctx["dump"].write_bytes(b"no es gzip")
        r = _ejecutar(ctx, dump=ctx["dump"])
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "gzip_invalid"
        assert "createdb" not in ctx["db"].read_text(encoding="utf-8")

    def test_recuento_distinto_falla(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, dump=ctx["dump"], extra_env={"FAKE_FILES": "4"})
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "recuento_distinto"

    def test_psql_roto_falla_y_borra_la_temporal(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, dump=ctx["dump"], extra_env={"FAKE_PSQL_FAIL": "1"})
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "restore_failed"
        assert "dropdb" in ctx["db"].read_text(encoding="utf-8")

    def test_manifiesto_ausente_avisa(self, tmp_path):
        ctx = _preparar(tmp_path)
        ctx["manifest"].unlink()
        r = _ejecutar(ctx, dump=ctx["dump"])
        assert r.returncode == 2
        estado = _estado(ctx)
        assert estado["status"] == "warning"
        assert estado["error"] == "manifest_ausente"
        assert estado["tablas"] == 28

    def test_manifiesto_sin_codigo_desplegado_avisa(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["codigo_desplegado_sha_completo"] = ""
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode == 2
        estado = _estado(ctx)
        assert estado["status"] == "warning"
        assert estado["error"] == "manifest_sin_codigo_desplegado"

    def test_sha_del_manifiesto_no_coincide(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["sha256"] = "0" * 64
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "manifest_no_coincide"
