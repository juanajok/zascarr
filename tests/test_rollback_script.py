"""Pruebas de `scripts/rollback.sh` (123a-ii, casos 04/05/06/07).

El pre-check de compatibilidad debe leer `version_num` del dump y la revisión
esperada del destino **antes** de la copia de seguridad y del `dropdb`.
Se ejecuta el script real con un `docker` falso; el `git` es real en un repo
temporal con dos commits.
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
cmd="$*"
if [[ "$cmd" == *"compose version"* ]]; then
    echo "Docker Compose version v2"
    exit 0
fi
if [[ "$cmd" == "info" ]]; then
    exit 0
fi
if [[ "$cmd" == *"pg_database_size"* ]]; then
    echo "${FAKE_DB_SIZE_KB:-1024}"
    exit 0
fi
if [[ "$cmd" == *"pg_dump"* ]]; then
    cat "$FAKE_DB_DUMP_SQL"
    exit 0
fi
if [[ "$cmd" == *" psql"* ]]; then
    if [[ "$cmd" == *" -c "* || "$cmd" == *" -tAc "* || "$cmd" == *" -At "* ]]; then
        if [[ "$cmd" == *"version_num"* ]]; then
            echo "${FAKE_DB_ALEMBIC:-0002}"
            exit 0
        fi
        if [[ "$cmd" == *"information_schema.tables"* ]]; then
            echo 1
            exit 0
        fi
        if [[ "$cmd" == *"count(*) FROM series"* || "$cmd" == *"count(*) from series"* ]]; then
            echo "${FAKE_DB_FILAS:-4/40/3}"
            exit 0
        fi
        echo ""
        exit 0
    fi
    cat >> "$RESTORE_LOG"
    exit 0
fi
if [[ "$cmd" == *"dropdb"* ]]; then
    echo "dropdb" >> "$DB_LOG"
    exit 0
fi
if [[ "$cmd" == *"createdb"* ]]; then
    echo "createdb" >> "$DB_LOG"
    exit 0
fi
if [[ "$cmd" == *" stop "* || "$cmd" == *" build "* || "$cmd" == *" up -d "* ]]; then
    echo "$cmd" >> "$DB_LOG"
    exit 0
fi
exit 0
"""

DF_FALSO = """#!/usr/bin/env bash
set -euo pipefail
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
printf '/ 100000000 1 %s 1%% /\\n' "${FAKE_DF_KB:-99999999}"
"""

CURL_FALSO = """#!/usr/bin/env bash
set -euo pipefail
echo "curl $*" >> "$CURL_LOG"
echo '{"status":"healthy","checks":{"database":"ok"}}'
exit 0
"""


def _sql(
    *,
    version: str = "0002",
    tablas: tuple[str, ...] = (
        "alembic_version",
        "series",
        "files",
        "wishlist",
    ),
) -> str:
    lineas = ["--", "-- PostgreSQL database dump", "--"]
    for tabla in tablas:
        lineas.append(f"COPY public.{tabla} (id) FROM stdin;")
        if tabla == "alembic_version":
            lineas.append(version)
        else:
            lineas.append("1")
        lineas.append("\\.")
    return "\n".join(lineas) + "\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _preparar(tmp_path: Path, *, con_alembic: bool = True) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("rollback.sh", "_comun.sh", "_credenciales.sh", "_espacio.sh"):
        shutil.copy2(SCRIPTS / nombre, repo / "scripts" / nombre)
    (repo / "docker-compose.yml").write_text("name: zascarr-123a\n", encoding="utf-8")
    if con_alembic:
        (repo / "alembic" / "versions").mkdir(parents=True)
        (repo / "alembic" / "versions" / "0001.py").write_text(
            'revision = "0001"\ndown_revision = None\n', encoding="utf-8"
        )
        (repo / "alembic" / "versions" / "0002.py").write_text(
            'revision = "0002"\ndown_revision = "0001"\n', encoding="utf-8"
        )
    (repo / "README.md").write_text("target\n", encoding="utf-8")

    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "target")
    target = _git(repo, "rev-parse", "HEAD").stdout.strip()
    (repo / "README.md").write_text("candidate\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "candidate")

    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("DB_PASSWORD=test\n", encoding="utf-8")
    backup = tmp_path / "backup"
    backup.mkdir()
    dump = backup / "update_20261030_120000.sql.gz"
    dump.write_bytes(gzip.compress(_sql().encode("utf-8")))

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nombre, contenido in (("docker", DOCKER_FALSO), ("curl", CURL_FALSO), ("df", DF_FALSO)):
        ruta = bin_ / nombre
        ruta.write_text(contenido, encoding="utf-8")
        ruta.chmod(0o755)

    logs = {}
    for nombre in ("stub", "db", "restore", "curl"):
        ruta = tmp_path / f"{nombre}.log"
        ruta.write_text("", encoding="utf-8")
        logs[nombre] = ruta

    safety_sql = tmp_path / "seguridad.sql"
    safety_sql.write_text(_sql(version="0002"), encoding="utf-8")

    return {
        "repo": repo,
        "target": target,
        "root": root,
        "backup": backup,
        "dump": dump,
        "bin": bin_,
        "safety_sql": safety_sql,
        **logs,
    }


def _manifest(ctx: dict, *, alembic: str | None = "0002", destino: str | None = None) -> Path:
    datos = {
        "schema": 1,
        "backup": ctx["dump"].name,
        "sha256": hashlib.sha256(ctx["dump"].read_bytes()).hexdigest(),
        "bytes": ctx["dump"].stat().st_size,
        "codigo_destino_sha_completo": destino if destino is not None else ctx["target"],
        "alembic": alembic,
    }
    if alembic is None:
        datos.pop("alembic")
    manifest = ctx["dump"].with_name(
        "MANIFIESTO-" + ctx["dump"].name.removesuffix(".sql.gz") + ".json"
    )
    manifest.write_text(json.dumps(datos), encoding="utf-8")
    return manifest


def _ejecutar(
    ctx: dict,
    *,
    args: list[str] | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{ctx['bin']}:{env['PATH']}",
            "ZASCARR_REPO": str(ctx["repo"]),
            "ZASCARR_ROOT": str(ctx["root"]),
            "BACKUP_DIR": str(ctx["backup"]),
            "DB_NAME": "zascarr",
            "DB_USER": "comics_admin",
            "HEALTH_URL": "http://127.0.0.1:18000/api/health",
            "HEALTH_TIMEOUT": "5",
            "FAKE_DB_DUMP_SQL": str(ctx["safety_sql"]),
            "STUB_LOG": str(ctx["stub"]),
            "DB_LOG": str(ctx["db"]),
            "RESTORE_LOG": str(ctx["restore"]),
            "CURL_LOG": str(ctx["curl"]),
        }
    )
    if extra_env:
        env.update(extra_env)
    if args is None:
        args = ["--sha", ctx["target"], "--backup", str(ctx["dump"]), "--yes"]
    return subprocess.run(
        ["bash", str(ctx["repo"] / "scripts" / "rollback.sh"), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


def _log(ctx: dict, nombre: str) -> str:
    return ctx[nombre].read_text(encoding="utf-8")


def _no_destructivo(ctx: dict) -> None:
    stub = _log(ctx, "stub")
    assert "dropdb" not in stub
    assert " stop " not in stub
    assert "pg_dump" not in stub
    assert not list(ctx["backup"].glob("rollback-safety_*.sql.gz"))


@pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")
class TestPrecheckRollback:
    def test_sin_espacio_aborta_antes_de_tocar_la_bd(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx)
        r = _ejecutar(ctx, extra_env={"FAKE_DF_KB": "1"})
        assert r.returncode != 0
        _no_destructivo(ctx)
        assert "espacio" in (r.stdout + r.stderr).lower()

    def test_manifiesto_correcto_pasa_y_el_flujo_existente_sigue(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx)
        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Revisión compatible" in r.stdout
        assert "dropdb" in _log(ctx, "db")
        assert list(ctx["backup"].glob("rollback-safety_*.sql.gz"))
        assert _git(ctx["repo"], "rev-parse", "HEAD").stdout.strip() == ctx["target"]

    def test_revision_distinta_aborta_antes_del_dropdb(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx, alembic="0001")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "Revisión incompatible" in r.stderr or "revisión" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_manifiesto_ausente_deriva_la_cabeza_del_destino(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stdout + r.stderr
        assert "alembic/versions" in r.stdout
        assert "dropdb" in _log(ctx, "db")

    def test_manifiesto_ausente_sin_alembic_en_el_destino_aborta(self, tmp_path):
        ctx = _preparar(tmp_path, con_alembic=False)
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "manifiesto" in r.stderr.lower() or "alembic" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_manifiesto_sin_alembic_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx, alembic=None)
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "alembic" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_manifiesto_con_otro_codigo_destino_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx, destino="f" * 40)
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "destino" in r.stderr.lower() or "código" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_dump_vacio_se_rechaza_antes_del_dropdb(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx)
        ctx["dump"].write_bytes(b"")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "vacío" in r.stderr.lower() or "empty" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_gzip_corrupto_se_rechaza_antes_del_dropdb(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx)
        ctx["dump"].write_bytes(b"no es gzip")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "gzip" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_gzip_sin_tablas_se_rechaza_antes_del_dropdb(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx)
        ctx["dump"].write_bytes(gzip.compress(_sql(tablas=("alembic_version",)).encode()))
        datos = json.loads(_manifest(ctx).read_text(encoding="utf-8"))
        datos["sha256"] = hashlib.sha256(ctx["dump"].read_bytes()).hexdigest()
        datos["bytes"] = ctx["dump"].stat().st_size
        _manifest(ctx).write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "tabla" in r.stderr.lower() or "falta" in r.stderr.lower()
        _no_destructivo(ctx)

    def test_dry_run_muestra_el_precheck_y_no_escribe(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx)
        r = _ejecutar(
            ctx,
            args=[
                "--sha",
                ctx["target"],
                "--backup",
                str(ctx["dump"]),
                "--dry-run",
            ],
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Revisión compatible" in r.stdout
        assert "Simulación" in r.stdout
        _no_destructivo(ctx)

    def test_forzar_no_salta_el_precheck(self, tmp_path):
        ctx = _preparar(tmp_path)
        _manifest(ctx, alembic="0001")
        r = _ejecutar(
            ctx,
            args=[
                "--sha",
                ctx["target"],
                "--backup",
                str(ctx["dump"]),
                "--forzar",
                "--yes",
            ],
        )
        assert r.returncode != 0
        assert "Revisión incompatible" in r.stderr or "revisión" in r.stderr.lower()
        _no_destructivo(ctx)
