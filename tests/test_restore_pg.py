"""Restauración real en el Postgres de CI (#334 B2).

Usa `TEST_DATABASE_URL` como base fuente: dumpea el esquema/datos de pruebas,
restaura en una base desechable y comprueba recuentos y esquema. Un `docker`
falso traduce `compose ... exec -T postgres CMD` al `CMD` del host con `PG*`;
así el script real se ejecuta igual que en la Pi, sin arrancar la app.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not all(
        shutil.which(c) for c in ("psql", "pg_dump", "createdb", "dropdb")
    ),
    reason="requiere TEST_DATABASE_URL y los clientes de PostgreSQL",
)

DOCKER_FALSO = """#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  *"compose version"*) echo "Docker Compose version v2"; exit 0 ;;
  *" postgres df -Pk /var/lib/postgresql/data"*)
    printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
    printf '/ %s 1 %s 1%% /\n' "${FAKE_PG_FREE_KB:-99999999}" "${FAKE_PG_FREE_KB:-99999999}"
    exit 0 ;;
  *"info"*) exit 0 ;;
esac
args=("$@")
for i in "${!args[@]}"; do
  if [[ "${args[$i]}" == "postgres" ]]; then
    exec "${args[@]:$((i+1))}"
  fi
done
exec "${args[@]}"
"""


def _pg_env() -> dict:
    url = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    u = urlparse(url)
    return {
        "PGHOST": u.hostname or "127.0.0.1",
        "PGPORT": str(u.port or 5432),
        "PGUSER": unquote(u.username or ""),
        "PGPASSWORD": unquote(u.password or ""),
        "PGDATABASE": u.path.lstrip("/"),
    }


def _psql(pg: dict, sql: str) -> str:
    return subprocess.run(
        ["psql", "-At", "-c", sql], env={**os.environ, **pg},
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def _preparar(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("probar_restauracion.sh", "_comun.sh", "_credenciales.sh", "_espacio.sh"):
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

    pg = _pg_env()
    fuente = {
        "files": int(_psql(pg, "select count(*) from files")),
        "series": int(_psql(pg, "select count(*) from series")),
        "issues": int(_psql(pg, "select count(*) from issues")),
        "wishlist": int(_psql(pg, "select count(*) from wishlist")),
        "alembic": _psql(pg, "select version_num from alembic_version"),
        "tablas": int(_psql(
            pg, "select count(*) from information_schema.tables where table_schema='public'"
        )),
    }
    dump = backup / "backup_pg_test.sql.gz"
    volcado = subprocess.run(
        ["pg_dump", "--format=plain", "--no-owner", "--no-privileges", pg["PGDATABASE"]],
        env={**os.environ, **pg}, check=True, capture_output=True,
    ).stdout
    dump.write_bytes(gzip.compress(volcado))
    sha = hashlib.sha256(dump.read_bytes()).hexdigest()
    manifest = backup / "MANIFIESTO-backup_pg_test.json"
    manifest.write_text(json.dumps({
        "backup": dump.name, "sha256": sha, "bytes": dump.stat().st_size,
        "alembic": fuente["alembic"],
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
    return {
        "repo": repo, "root": root, "backup": backup, "offsite": offsite,
        "status": status, "dump": dump, "manifest": manifest, "bin": bin_,
        "stub": stub, "pg": pg, "fuente": fuente,
    }


def test_restaura_en_base_desechable_sin_arrancar_la_app(tmp_path):
    ctx = _preparar(tmp_path)
    env = {
        **os.environ, **ctx["pg"],
        # El script usa DB_USER (no PGUSER) para -U; en la Pi coincide con el
        # usuario del compose, en CI es el usuario de TEST_DATABASE_URL.
        "DB_USER": ctx["pg"]["PGUSER"],
        "PATH": f"{ctx['bin']}:{os.environ['PATH']}",
        "ZASCARR_REPO": str(ctx["repo"]),
        "ZASCARR_ROOT": str(ctx["root"]),
        "BACKUP_DIR": str(ctx["backup"]),
        "BACKUP_OFFSITE_DIR": str(ctx["offsite"]),
        "BACKUP_STATUS_DIR": str(ctx["status"]),
        "RESTORE_STATUS_FILE": str(ctx["status"] / "restore-status.json"),
        "STUB_LOG": str(ctx["stub"]),
    }
    r = subprocess.run(
        ["bash", str(ctx["repo"] / "scripts" / "probar_restauracion.sh"),
         "--dump", str(ctx["dump"]), "--manifest", str(ctx["manifest"])],
        env=env, capture_output=True, text=True, timeout=180,
        stdin=subprocess.DEVNULL,
    )
    assert r.returncode == 0, r.stdout + r.stderr

    estado = json.loads((ctx["status"] / "restore-status.json").read_text(encoding="utf-8"))
    assert estado["status"] == "ok"
    assert estado["tablas"] == ctx["fuente"]["tablas"]
    assert estado["alembic"] == ctx["fuente"]["alembic"]
    assert estado["recuentos"] == {
        "files": ctx["fuente"]["files"],
        "series": ctx["fuente"]["series"],
        "issues": ctx["fuente"]["issues"],
        "wishlist": ctx["fuente"]["wishlist"],
    }

    # La fuente no se toca y la base temporal se borra.
    assert int(_psql(ctx["pg"], "select count(*) from files")) == ctx["fuente"]["files"]
    assert _psql(
        ctx["pg"],
        "select count(*) from pg_database where datname like 'zascarr_restore_%'",
    ) == "0"

    # La app no se arranca: el único `docker` es el falso, y no hay servicio zascarr.
    log = ctx["stub"].read_text(encoding="utf-8").replace("zascarr_restore_", "")
    assert "zascarr" not in log
