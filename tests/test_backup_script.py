"""Pruebas de scripts/backup.sh (#334) con un `docker` falso y directorios temporales.

No necesitan PostgreSQL ni el disco real: el script se ejecuta tal cual, con un
`docker` de mentira en PATH que responde a pg_dump/psql. Cubren el camino feliz y
los fallos que importan: pg_dump caído, dump sin cabecera, montaje ausente, offsite
no escribible y hash del offsite manipulado.
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
SCRIPTS = RAIZ / "scripts"

DOCKER_FALSO = """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "compose" && "${2:-}" == "version" ]]; then
    echo "Docker Compose version v2"
    exit 0
fi
if [[ "${1:-}" == "info" ]]; then
    exit 0
fi
if [[ "$*" == *" postgres pg_dump "* ]]; then
    case "${FAKE_MODE:-ok}" in
        fail) echo "pg_dump: boom" >&2; exit 1 ;;
        partial) printf -- '-- partial\\n'; exit 0 ;;
        *) cat "${FIXTURE_SQL:?}" ;;
    esac
fi
if [[ "$*" == *"psql"* ]]; then
    # Como `docker compose exec`: consume stdin. Sin esto, el stub no reproduce
    # el bucle que pierde nombres al llamar a escribir_manifiesto.
    cat >/dev/null 2>&1 || true
    echo "0020"
    exit 0
fi
exit 0
"""

CP_FALSO = """#!/usr/bin/env bash
set -euo pipefail
"${REAL_CP:?}" "$@"
for ultimo in "$@"; do :; done
if [[ "${ultimo}" == "${OFFSITE_DIR:?}"/* && "${ultimo}" == *".sql.gz"* ]]; then
    printf 'x' >> "${ultimo}"
fi
"""

MV_TRUNCA = """#!/usr/bin/env bash
set -euo pipefail
"${REAL_MV:?}" "$@"
for ultimo in "$@"; do :; done
if [[ "${ultimo}" == *.sql.gz ]]; then
    truncate -s $(( $(stat -c %s "${ultimo}") / 2 )) "${ultimo}"
fi
"""

DF_FALSO = """#!/usr/bin/env bash
set -euo pipefail
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
printf '/ 100000000 1 %s 1%% /\\n' "${FAKE_DF_KB:-99999999}"
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


def _sin_copy(sql: str, tabla: str) -> str:
    """El SQL sin el bloque `COPY public.<tabla> … \\.`."""
    salida, dentro = [], False
    for linea in sql.splitlines():
        if linea.startswith(f"COPY public.{tabla} "):
            dentro = True
            continue
        if dentro:
            dentro = linea != "\\."
            continue
        salida.append(linea)
    return "\n".join(salida) + "\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )


def _preparar(tmp_path: Path) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    for nombre in ("backup.sh", "_comun.sh", "_credenciales.sh", "_espacio.sh"):
        shutil.copy2(SCRIPTS / nombre, repo / "scripts" / nombre)
    (repo / "docker-compose.yml").write_text("", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")

    root = tmp_path / "root"
    root.mkdir()
    (root / ".env").write_text("DB_PASSWORD=test\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(DOCKER_FALSO, encoding="utf-8")
    docker.chmod(0o755)
    df = bin_dir / "df"
    df.write_text(DF_FALSO, encoding="utf-8")
    df.chmod(0o755)

    fixture = tmp_path / "fixture.sql"
    fixture.write_text(FIXTURE_SQL, encoding="utf-8")

    backup = tmp_path / "backup"
    backup.mkdir()
    offsite = tmp_path / "offsite"
    offsite.mkdir()
    status = tmp_path / "status"
    status.mkdir()

    return {
        "repo": repo,
        "root": root,
        "bin": bin_dir,
        "fixture": fixture,
        "backup": backup,
        "offsite": offsite,
        "status": status,
        "lock": tmp_path / "lock",
    }


def _ejecutar(
    ctx: dict,
    *,
    mode: str = "ok",
    mount: str = "/",
    offsite: Path | None = None,
    extra_env: dict | None = None,
):
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{ctx['bin']}:{env['PATH']}",
            "FIXTURE_SQL": str(ctx["fixture"]),
            "FAKE_MODE": mode,
            "ZASCARR_REPO": str(ctx["repo"]),
            "ZASCARR_ROOT": str(ctx["root"]),
            "BACKUP_DIR": str(ctx["backup"]),
            "BACKUP_OFFSITE_DIR": str(offsite if offsite is not None else ctx["offsite"]),
            "BACKUP_OFFSITE_MOUNT": mount,
            "BACKUP_SKIP_DEVICE_CHECK": "1",
            "BACKUP_STATUS_DIR": str(ctx["status"]),
            "BACKUP_LOCK_FILE": str(ctx["lock"]),
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["bash", str(ctx["repo"] / "scripts" / "backup.sh")],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


def _estado(ctx: dict) -> dict:
    return json.loads((ctx["status"] / "status.json").read_text(encoding="utf-8"))


@pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")
class TestBackupScript:
    def test_copia_local_y_offsite_verificada(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stdout + r.stderr

        locales = list(ctx["backup"].glob("backup_*.sql.gz"))
        offsite = list(ctx["offsite"].glob("backup_*.sql.gz"))
        assert len(locales) == 1 and len(offsite) == 1
        assert locales[0].read_bytes() == offsite[0].read_bytes()
        assert (locales[0].stat().st_mode & 0o777) == 0o600
        assert (offsite[0].stat().st_mode & 0o777) == 0o600

        manifiesto = ctx["backup"] / f"MANIFIESTO-{locales[0].name.removesuffix('.sql.gz')}.json"
        datos = json.loads(manifiesto.read_text(encoding="utf-8"))
        assert datos["sha256"] == hashlib.sha256(locales[0].read_bytes()).hexdigest()
        assert datos["bytes"] == locales[0].stat().st_size
        assert datos["alembic"] == "0020"
        assert datos["codigo_desplegado_sha_completo"]
        assert datos["offsite"]["verificada"] is True

        estado = _estado(ctx)
        assert estado["status"] == "ok"
        assert estado["offsite"] is True
        assert estado["sha256"] == datos["sha256"]
        assert (ctx["status"] / "status.json").stat().st_mode & 0o777 == 0o644

    def test_pg_dump_falla_no_publica_copia(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, mode="fail")
        assert r.returncode != 0
        assert _estado(ctx)["status"] == "failed"
        assert _estado(ctx)["error"] == "pg_dump_failed"
        assert not list(ctx["backup"].glob("backup_*.sql.gz"))
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))

    def test_sin_espacio_no_volca_ni_publica(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DF_KB": "1024"})
        assert r.returncode != 0
        assert _estado(ctx)["error"] == "disk_full"
        assert not list(ctx["backup"].glob("backup_*.sql.gz"))
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))

    def test_dump_sin_cabecera_no_se_publica(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, mode="partial")
        assert r.returncode != 0
        assert _estado(ctx)["status"] == "failed"
        assert _estado(ctx)["error"] == "header_missing"
        assert not list(ctx["backup"].glob("backup_*.sql.gz"))

    @pytest.mark.parametrize("tabla", ["alembic_version", "series", "files", "wishlist"])
    def test_dump_sin_una_tabla_requerida_no_se_publica(self, tmp_path, tabla):
        """Las cuatro tablas que `rollback.sh` necesita, una a una: sin cualquiera de ellas
        la copia se descarta, el estado dice `tables_missing` y no queda nada, ni local
        ni fuera del disco."""
        ctx = _preparar(tmp_path)
        ctx["fixture"].write_text(_sin_copy(FIXTURE_SQL, tabla), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert _estado(ctx)["status"] == "failed"
        assert _estado(ctx)["error"] == "tables_missing"
        assert f"falta la tabla {tabla}" in r.stdout + r.stderr
        assert not list(ctx["backup"].glob("backup_*.sql.gz"))
        assert not list(ctx["backup"].glob("MANIFIESTO-*.json"))
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))

    def test_un_volcado_que_se_corta_al_publicarse_se_descarta_con_gzip_invalid(self, tmp_path):
        """`volcar_postgres` comprueba `gzip -t` sobre el temporal; `verificar_dump` lo repite
        sobre el fichero ya publicado. Aquí el `mv` corta el .gz a la mitad (como un disco que
        falla justo al escribir): el temporal estaba bien, el definitivo no, y esa segunda
        comprobación es la que lo detiene con su propia causa."""
        ctx = _preparar(tmp_path)
        mv = ctx["bin"] / "mv"
        mv.write_text(MV_TRUNCA, encoding="utf-8")
        mv.chmod(0o755)
        r = _ejecutar(ctx, extra_env={"REAL_MV": shutil.which("mv") or "/bin/mv"})
        assert r.returncode != 0
        assert _estado(ctx)["status"] == "failed"
        assert _estado(ctx)["error"] == "gzip_invalid"
        assert "gzip -t falla" in r.stdout + r.stderr
        assert not list(ctx["backup"].glob("backup_*.sql.gz"))
        assert not list(ctx["backup"].glob("MANIFIESTO-*.json"))
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))

    def test_montaje_ausente_avisa_y_no_escribe_offsite(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, mount=str(tmp_path / "no-montado"))
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "offsite_mount_missing"
        assert estado["offsite"] is False
        assert len(list(ctx["backup"].glob("backup_*.sql.gz"))) == 1
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))

    def test_offsite_no_escribible_avisa(self, tmp_path):
        ctx = _preparar(tmp_path)
        no_dir = tmp_path / "no-es-dir"
        no_dir.write_text("x", encoding="utf-8")
        r = _ejecutar(ctx, offsite=no_dir)
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "offsite_copy_failed"
        assert len(list(ctx["backup"].glob("backup_*.sql.gz"))) == 1

    def test_hash_del_offsite_manipulado_se_detecta(self, tmp_path):
        ctx = _preparar(tmp_path)
        cp_falso = ctx["bin"] / "cp"
        cp_falso.write_text(CP_FALSO, encoding="utf-8")
        cp_falso.chmod(0o755)
        r = _ejecutar(
            ctx,
            extra_env={
                "REAL_CP": shutil.which("cp") or "/bin/cp",
                "OFFSITE_DIR": str(ctx["offsite"]),
            },
        )
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "offsite_verify_failed"
        assert len(list(ctx["backup"].glob("backup_*.sql.gz"))) == 1
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))

    def test_sincroniza_todas_las_anclas_al_offsite(self, tmp_path):
        """Regresión: el bucle de anclas no puede perder nombres porque
        `escribir_manifiesto` (docker compose exec) consuma su stdin."""
        ctx = _preparar(tmp_path)
        sha = _git(ctx["repo"], "rev-parse", "HEAD").stdout.strip()
        anclas = [f"2026100{d}_000000" for d in range(1, 6)]
        for ts in anclas:
            _git(ctx["repo"], "update-ref", f"refs/zascarr/update/{ts}", sha)
            (ctx["backup"] / f"update_{ts}.sql.gz").write_bytes(f"ancla-{ts}".encode())

        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stdout + r.stderr

        fuera = sorted(p.name for p in ctx["offsite"].glob("update_*.sql.gz"))
        assert fuera == sorted(f"update_{ts}.sql.gz" for ts in anclas)
        for ts in anclas:
            assert (ctx["offsite"] / f"MANIFIESTO-update_{ts}.json").is_file()

        estado = _estado(ctx)
        assert estado["status"] == "ok"
        assert len(estado["retencion_protegida"]) == len(anclas)
