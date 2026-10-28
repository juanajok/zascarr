"""El manifiesto del dump de rescate debe llevar el commit NUEVO, no el viejo.

Regresión de #334: `update.sh` escribía el manifiesto antes del fast-forward, así
que `codigo_desplegado` quedaba igual a `codigo_destino` (el commit anterior).
El test monta un repo local y un `origin` con un commit nuevo; el `update.sh` real
hace el fast-forward y el manifiesto debe declarar el commit nuevo.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("git") is None or shutil.which("curl") is None,
    reason="requiere git y curl",
)

DOCKER_FALSO = """#!/bin/sh
echo "docker $*" >> "$STUB_LOG"
case "$*" in
  *"compose version"*) echo "Docker Compose version v2"; exit 0 ;;
  *"pg_dump"*) cat "$FIXTURE_SQL"; exit 0 ;;
  *"psql"*) cat >/dev/null 2>&1 || true; echo "0020"; exit 0 ;;
esac
exit 0
"""

CURL_FALSO = """#!/bin/sh
exit 0
"""

FIXTURE_SQL = """--
-- PostgreSQL database dump
--
COPY public.alembic_version (version_num) FROM stdin;
0020
\\.
COPY public.series (id) FROM stdin;
\\.
COPY public.files (id) FROM stdin;
\\.
COPY public.wishlist (id) FROM stdin;
\\.
"""


def _git(repo: Path, *args: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True, env=env
    )


def _preparar(tmp_path: Path):
    raiz = tmp_path / "opt" / "zascarr"
    repo = raiz / "zascarr"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("docker-compose.yml", ".env.example"):
        shutil.copy(RAIZ / nombre, repo / nombre)
    for fichero in (RAIZ / "scripts").glob("*.sh"):
        shutil.copy(fichero, repo / "scripts" / fichero.name)
    (raiz / ".env").write_text(
        "DB_PASSWORD=Sint3tica-Update-Manifiesto\n", encoding="utf-8"
    )
    (raiz / ".env").chmod(0o600)

    entorno = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    _git(repo, "init", "-q", "-b", "main", env=entorno)
    _git(repo, "add", ".", env=entorno)
    _git(repo, "commit", "-q", "-m", "inicial", env=entorno)
    prev = _git(repo, "rev-parse", "HEAD", env=entorno).stdout.strip()

    bare = tmp_path / "origin.git"
    subprocess.run(
        ["git", "init", "--bare", "-q", "-b", "main", str(bare)],
        check=True, capture_output=True, env=entorno,
    )
    _git(repo, "remote", "add", "origin", str(bare), env=entorno)
    _git(repo, "push", "-q", "-u", "origin", "main", env=entorno)

    work = tmp_path / "work"
    subprocess.run(
        ["git", "clone", "-q", str(bare), str(work)],
        check=True, capture_output=True, env=entorno,
    )
    (work / "NUEVO.txt").write_text("nuevo\n", encoding="utf-8")
    _git(work, "add", ".", env=entorno)
    _git(work, "commit", "-q", "-m", "nuevo", env=entorno)
    _git(work, "push", "-q", "origin", "main", env=entorno)
    nuevo = _git(bare, "rev-parse", "main", env=entorno).stdout.strip()

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "docker").write_text(DOCKER_FALSO, encoding="utf-8")
    (bin_ / "docker").chmod(0o755)
    (bin_ / "curl").write_text(CURL_FALSO, encoding="utf-8")
    (bin_ / "curl").chmod(0o755)
    fixture = tmp_path / "fixture.sql"
    fixture.write_text(FIXTURE_SQL, encoding="utf-8")
    log = tmp_path / "docker.log"
    log.write_text("", encoding="utf-8")
    return repo, raiz, bin_, log, entorno, prev, nuevo, fixture


def test_manifiesto_del_dump_de_rescate_lleva_el_commit_nuevo(tmp_path):
    repo, _raiz, bin_, log, entorno, prev, nuevo, fixture = _preparar(tmp_path)
    assert prev != nuevo

    backup = tmp_path / "backups"
    r = subprocess.run(
        ["bash", str(repo / "scripts" / "update.sh")],
        capture_output=True, text=True, timeout=180, check=False,
        stdin=subprocess.DEVNULL,
        env={
            **entorno,
            "PATH": f"{bin_}:{os.environ['PATH']}",
            "STUB_LOG": str(log),
            "FIXTURE_SQL": str(fixture),
            "BACKUP_DIR": str(backup),
            "HEALTH_TIMEOUT": "2",
            "BRANCH": "main",   # desde #351 update.sh exige la rama; este es el despliegue de `main` del origen sintético
        },
    )
    assert r.returncode == 0, r.stdout + r.stderr

    refs = _git(
        repo, "for-each-ref", "refs/zascarr/update", "--format=%(refname:short)", env=entorno
    ).stdout.strip().splitlines()
    assert len(refs) == 1, refs
    ts = refs[0].rsplit("/", 1)[-1]

    manifiesto = backup / f"MANIFIESTO-update_{ts}.json"
    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    assert datos["codigo_destino_sha_completo"] == prev
    assert datos["codigo_desplegado_sha_completo"] == nuevo
    assert datos["referencia_emparejada"] == f"refs/zascarr/update/{ts}"
    assert datos["cubre_rollback_de_codigo"] is True

    dump = backup / f"update_{ts}.sql.gz"
    assert datos["sha256"] == hashlib.sha256(dump.read_bytes()).hexdigest()
    assert datos["bytes"] == dump.stat().st_size
    assert datos["alembic"] == "0020"
