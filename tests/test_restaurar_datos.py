"""Pruebas de `scripts/restaurar_datos.sh` (123a-i, caso 10).

El script se ejecuta tal cual, con un `docker` falso en PATH que traduce
`compose config`, `pg_dump`, `psql`, `dropdb`, `createdb`, `stop` y `up -d`.
No se necesita PostgreSQL real: lo que se prueba es el contrato de seguridad
(HEAD, manifiesto, Alembic antes del `dropdb`, copia previa, recuperación y
ausencia de `git reset`/`build`).
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
SCRIPT = RAIZ / "scripts" / "restaurar_datos.sh"

DOCKER_FALSO = r"""#!/usr/bin/env bash
set -euo pipefail
echo "docker $*" >> "$STUB_LOG"
cmd="$*"
if [[ "$cmd" == *" config --format json"* ]]; then
    cat "$FAKE_COMPOSE_JSON"
    exit 0
fi
if [[ "$cmd" == *" df -Pk "* ]]; then
    printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
    printf '/ %s 1 %s 1%% /\n' "${FAKE_PG_FREE_KB:-99999999}" "${FAKE_PG_FREE_KB:-99999999}"
    exit 0
fi
if [[ "$cmd" == *"pg_dump"* ]]; then
    if [[ "${FAKE_PGDUMP_FAIL:-0}" == "1" ]]; then
        echo "pg_dump: boom" >&2
        exit 1
    fi
    cat "$FAKE_DB_DUMP_SQL"
    exit 0
fi
if [[ "$cmd" == *"pg_database_size"* ]]; then
    echo "${FAKE_DB_SIZE_KB:-1024}"
    exit 0
fi
if [[ "$cmd" == *" psql"* ]]; then
    if [[ "$cmd" == *" -c "* ]]; then
        if [[ "$cmd" == *"version_num"* ]]; then
            if [[ -s "$RESTORE_LOG" && -n "${FAKE_DB_ALEMBIC_POST:-}" ]]; then
                echo "$FAKE_DB_ALEMBIC_POST"
            else
                echo "${FAKE_DB_ALEMBIC:-0020}"
            fi
            exit 0
        fi
        if [[ "$cmd" == *"left join"* ]]; then
            echo "${FAKE_DB_ORPHANS:-0|0|0|0}"
            exit 0
        fi
        if [[ "$cmd" == *"count(*) from series"* ]]; then
            echo "${FAKE_DB_COUNTS:-2|1|3|1|1}"
            exit 0
        fi
        echo ""
        exit 0
    fi
    # Restauración por stdin: el contenido llega al log para saber qué se aplicó.
    cat >> "$RESTORE_LOG"
    if [[ "${FAKE_RESTORE_FAIL:-0}" == "1" && ! -f "$RESTORE_FAIL_MARK" ]]; then
        : > "$RESTORE_FAIL_MARK"
        echo "restore: boom" >&2
        exit 1
    fi
    exit 0
fi
if [[ "$cmd" == *"dropdb"* ]]; then
    if [[ "${FAKE_DROP_FAIL:-0}" == "1" ]]; then
        echo "dropdb: boom" >&2
        exit 1
    fi
    exit 0
fi
if [[ "$cmd" == *"createdb"* || "$cmd" == *" stop "* || "$cmd" == *" up -d "* ]]; then
    exit 0
fi
exit 0
"""

CURL_FALSO = """#!/usr/bin/env bash
set -euo pipefail
echo "curl $*" >> "$CURL_LOG"
if [[ -n "${FAKE_HEALTH_FALLOS:-}" ]]; then
    n=0
    [[ -f "$HEALTH_CONTADOR" ]] && n=$(cat "$HEALTH_CONTADOR")
    n=$((n + 1))
    echo "$n" > "$HEALTH_CONTADOR"
    if (( n <= FAKE_HEALTH_FALLOS )); then
        exit 22
    fi
    echo '{"status":"healthy","checks":{"database":"ok"}}'
    exit 0
fi
if [[ "${FAKE_HEALTH:-ok}" == "ok" ]]; then
    echo '{"status":"healthy","checks":{"database":"ok"}}'
    exit 0
fi
if [[ "${FAKE_HEALTH:-ok}" == "db_error" ]]; then
    echo '{"status":"unhealthy","checks":{"database":"error"}}'
    exit 0
fi
exit 22
"""

GIT_FALSO = """#!/usr/bin/env bash
set -euo pipefail
echo "git $*" >> "$GIT_LOG"
exec "${REAL_GIT:?}" "$@"
"""


def _sql(
    *,
    series: int = 2,
    issues: int = 1,
    files: int = 3,
    operaciones: int = 1,
    wishlist: int = 1,
    alembic: str = "0020",
    marca: str = "destino",
) -> str:
    lineas = ["--", "-- PostgreSQL database dump", f"-- {marca}", "--"]
    for tabla in (
        "alembic_version",
        "series",
        "issues",
        "files",
        "vinculacion_operaciones",
        "wishlist",
    ):
        lineas.append(f"CREATE TABLE public.{tabla} (id integer);")
    lineas += ["COPY public.alembic_version (version_num) FROM stdin;", alembic, "\\."]
    for tabla, n in (
        ("series", series),
        ("issues", issues),
        ("files", files),
        ("vinculacion_operaciones", operaciones),
        ("wishlist", wishlist),
    ):
        lineas.append(f"COPY public.{tabla} (id) FROM stdin;")
        lineas += [str(i) for i in range(n)]
        lineas.append("\\.")
    return "\n".join(lineas) + "\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _manifest(dump: Path, head: str, *, alembic: str = "0020") -> dict:
    return {
        "schema": 1,
        "backup": dump.name,
        "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "bytes": dump.stat().st_size,
        "codigo_destino_sha_completo": "a" * 40,
        "codigo_desplegado_sha_completo": head,
        "alembic": alembic,
        "created_at": "2026-10-29T21:05:27+01:00",
        "origin": "test",
        "id": "test-1",
    }


def _preparar(tmp_path: Path, *, sql: str | None = None) -> dict:
    repo = tmp_path / "repo"
    (repo / "scripts").mkdir(parents=True)
    (repo / "README.md").write_text("repo\n", encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "add", ".")
    _git(repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")
    head = _git(repo, "rev-parse", "HEAD").stdout.strip()

    root = tmp_path / "root"
    root.mkdir()
    env_file = root / ".env"
    env_file.write_text("DB_PASSWORD=test\n", encoding="utf-8")
    compose = root / "docker-compose.yml"
    compose.write_text("name: zascarr-123a\n", encoding="utf-8")
    backup = root / "backup"
    backup.mkdir()
    status = root / "status"
    status.mkdir()

    dump = backup / "update_20261029_210527.sql.gz"
    dump.write_bytes(gzip.compress((sql or _sql()).encode("utf-8")))
    manifest = backup / "MANIFIESTO-update_20261029_210527.json"
    manifest.write_text(json.dumps(_manifest(dump, head)), encoding="utf-8")

    safety_sql = _sql(marca="seguridad")
    safety_sql_path = tmp_path / "seguridad.sql"
    safety_sql_path.write_text(safety_sql, encoding="utf-8")

    compose_json = tmp_path / "compose.json"
    compose_json.write_text(
        json.dumps(
            {
                "name": "zascarr-123a",
                "services": {
                    "postgres": {"container_name": "zascarr-123a-db"},
                    "zascarr": {"container_name": "zascarr-123a-orquestador"},
                },
            }
        ),
        encoding="utf-8",
    )

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nombre, contenido in (
        ("docker", DOCKER_FALSO),
        ("curl", CURL_FALSO),
        ("git", GIT_FALSO),
    ):
        ruta = bin_ / nombre
        ruta.write_text(contenido, encoding="utf-8")
        ruta.chmod(0o755)

    logs = {}
    for nombre in ("stub", "restore", "curl", "git"):
        ruta = tmp_path / f"{nombre}.log"
        ruta.write_text("", encoding="utf-8")
        logs[nombre] = ruta

    return {
        "repo": repo,
        "head": head,
        "root": root,
        "env": env_file,
        "compose": compose,
        "backup": backup,
        "status": status,
        "dump": dump,
        "manifest": manifest,
        "safety_sql": safety_sql_path,
        "bin": bin_,
        "compose_json": compose_json,
        **logs,
    }


def _ejecutar(
    ctx: dict,
    *,
    args: list[str] | None = None,
    extra_env: dict | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{ctx['bin']}:{env['PATH']}",
            "REAL_GIT": shutil.which("git") or "/usr/bin/git",
            "REPO_DIR": str(ctx["repo"]),
            "ENV_FILE": str(ctx["env"]),
            "COMPOSE_FILE": str(ctx["compose"]),
            "BACKUP_DIR": str(ctx["backup"]),
            "DB_NAME": "zascarr",
            "DB_USER": "comics_admin",
            "HEALTH_URL": "http://127.0.0.1:18000/api/health",
            "HEALTH_TIMEOUT": "5",
            "FAKE_DB_DUMP_SQL": str(ctx["safety_sql"]),
            "FAKE_COMPOSE_JSON": str(ctx["compose_json"]),
            "STUB_LOG": str(ctx["stub"]),
            "RESTORE_LOG": str(ctx["restore"]),
            "RESTORE_FAIL_MARK": str(ctx["root"] / "restore-fail.marker"),
            "CURL_LOG": str(ctx["curl"]),
            "HEALTH_CONTADOR": str(ctx["root"] / "health-intentos.txt"),
            "GIT_LOG": str(ctx["git"]),
        }
    )
    if extra_env:
        env.update(extra_env)
    if args is None:
        args = [
            "--dump",
            str(ctx["dump"]),
            "--manifest",
            str(ctx["manifest"]),
            "--sha",
            ctx["head"],
            "--yes",
        ]
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        input=input_text,
        stdin=subprocess.DEVNULL if input_text is None else None,
    )


def _log(ctx: dict, nombre: str) -> str:
    return ctx[nombre].read_text(encoding="utf-8")


def _sin_destructivos(ctx: dict) -> None:
    stub = _log(ctx, "stub")
    for prohibido in ("dropdb", "createdb", "pg_dump", " stop ", " up -d "):
        assert prohibido not in stub, stub


@pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")
class TestRestaurarDatos:
    def test_dry_run_no_toca_nada(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                ctx["head"],
                "--dry-run",
            ],
        )
        assert r.returncode == 0, r.stdout + r.stderr
        _sin_destructivos(ctx)
        assert not list(ctx["backup"].glob("rollback-safety_*.sql.gz"))
        assert "dry-run" in (r.stdout + r.stderr).lower()

    def test_sin_espacio_aborta_antes_de_tocar_la_bd(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_PG_FREE_KB": "1"})
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "espacio" in (r.stdout + r.stderr).lower()

    def test_head_distinto_aborta_antes_de_tocar(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                "0" * 40,
                "--yes",
            ],
        )
        assert r.returncode != 0
        _sin_destructivos(ctx)

    def test_manifiesto_con_hash_distinto_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["sha256"] = "0" * 64
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "manifiesto" in r.stderr.lower()

    def test_manifiesto_con_bytes_distintos_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["bytes"] = datos["bytes"] + 1
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "tamaño" in r.stderr.lower() or "bytes" in r.stderr.lower()

    def test_manifiesto_ausente_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        ctx["manifest"].unlink()
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--sha",
                ctx["head"],
                "--yes",
            ],
        )
        assert r.returncode != 0
        _sin_destructivos(ctx)

    def test_manifiesto_con_schema_desconocido_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["schema"] = 2
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "schema" in r.stderr.lower()

    def test_manifiesto_sin_schema_avisa(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos.pop("schema", None)
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                ctx["head"],
                "--dry-run",
            ],
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "schema" in (r.stdout + r.stderr).lower()

    def test_manifiesto_de_otro_codigo_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["codigo_destino_sha_completo"] = "f" * 40
        datos["codigo_desplegado_sha_completo"] = "e" * 40
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "commit" in r.stderr.lower()

    def test_alembic_incompatible_aborta_antes_del_dropdb(self, tmp_path):
        ctx = _preparar(tmp_path, sql=_sql(alembic="0019"))
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                ctx["head"],
                "--alembic-esperada",
                "0020",
                "--yes",
            ],
        )
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "alembic" in r.stderr.lower() or "revisión" in r.stderr.lower()

    def test_proyecto_de_produccion_se_rechaza(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["compose_json"].read_text(encoding="utf-8"))
        datos["name"] = "zascarr"
        ctx["compose_json"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "proyecto" in r.stderr.lower()

    def test_arbol_sucio_aborta(self, tmp_path):
        ctx = _preparar(tmp_path)
        (ctx["repo"] / "README.md").write_text("modificado\n", encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        _sin_destructivos(ctx)
        assert "limpio" in r.stderr.lower() or "cambios" in r.stderr.lower()

    def test_fallo_al_restaurar_recupera_la_copia(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_RESTORE_FAIL": "1"})
        assert r.returncode != 0
        seguridad = list(ctx["backup"].glob("rollback-safety_*.sql.gz"))
        assert len(seguridad) == 1
        assert "seguridad" in _log(ctx, "restore")
        salida = r.stdout + r.stderr
        assert "recuper" in salida.lower() or "copia" in salida.lower()
        assert " build " not in _log(ctx, "stub")

    def test_exito_arranca_sin_build_ni_git_reset(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stdout + r.stderr
        stub = _log(ctx, "stub")
        assert " stop " in stub
        assert "dropdb" in stub and "createdb" in stub
        assert " up -d " in stub
        assert " build " not in stub
        git_log = _log(ctx, "git")
        assert " reset" not in git_log and " checkout" not in git_log
        assert "destino" in _log(ctx, "restore")
        assert list(ctx["backup"].glob("rollback-safety_*.sql.gz"))
        assert _git(ctx["repo"], "rev-parse", "HEAD").stdout.strip() == ctx["head"]

    def test_health_falla_recupera_la_copia(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            extra_env={"FAKE_HEALTH": "fail", "HEALTH_TIMEOUT": "1", "HEALTH_INTERVAL": "1"},
        )
        assert r.returncode != 0
        assert "seguridad" in _log(ctx, "restore")
        assert list(ctx["backup"].glob("rollback-safety_*.sql.gz"))

    def test_health_reintenta_hasta_que_la_app_arranca(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            extra_env={"FAKE_HEALTH_FALLOS": "2", "HEALTH_TIMEOUT": "10", "HEALTH_INTERVAL": "1"},
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert len(_log(ctx, "curl").splitlines()) >= 3
        assert "Datos restaurados sin cambiar el código" in r.stdout
        assert "3 intentos" in r.stdout

    def test_health_que_nunca_responde_recupera_y_falla(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            extra_env={"FAKE_HEALTH": "fail", "HEALTH_TIMEOUT": "2", "HEALTH_INTERVAL": "1"},
        )
        assert r.returncode != 0
        assert "Datos restaurados" not in r.stdout
        assert "seguridad" in _log(ctx, "restore")
        assert "health" in (r.stdout + r.stderr).lower()

    def test_sin_yes_pide_si_y_no_continua_con_no(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                ctx["head"],
            ],
            input_text="NO\n",
        )
        assert r.returncode != 0
        _sin_destructivos(ctx)

    def test_sin_yes_continua_con_si(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                ctx["head"],
            ],
            input_text="SI\n",
        )
        assert r.returncode == 0, r.stdout + r.stderr
        assert "dropdb" in _log(ctx, "stub")

    def test_forzar_esta_prohibido(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            args=[
                "--dump",
                str(ctx["dump"]),
                "--manifest",
                str(ctx["manifest"]),
                "--sha",
                ctx["head"],
                "--forzar",
            ],
        )
        assert r.returncode != 0 and "--forzar está prohibido" in r.stderr
        _sin_destructivos(ctx)

    def test_no_imprime_rutas_completas(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            extra_env={"FAKE_HEALTH": "fail", "HEALTH_TIMEOUT": "1", "HEALTH_INTERVAL": "1"},
        )
        salida = r.stdout + r.stderr
        assert str(ctx["dump"]) not in salida
        assert str(ctx["backup"]) not in salida


GZIP_QUE_FALLA_EN_LA_COPIA_PREVIA = """#!/usr/bin/env bash
if [[ "$1" == "-t" && "$2" == *rollback-safety_* ]]; then exit 1; fi
exec "${REAL_GZIP:?}" "$@"
"""


class TestGuardasDeLaRestauracion:
    """#123 (QA sobre #376, A2): cada guarda se discrimina con su propia prueba (antes sobrevivían a la mutación)."""

    def test_la_restauracion_pide_on_error_stop(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx)
        assert r.returncode == 0, r.stdout + r.stderr
        lineas = [x for x in _log(ctx, "stub").splitlines() if " psql " in x and " -q " in x]
        assert lineas and all("ON_ERROR_STOP=1" in x for x in lineas)

    @pytest.mark.parametrize("cuentas,tabla", [
        ("3|1|3|1|1", "series"), ("2|2|3|1|1", "issues"), ("2|1|4|1|1", "files"),
        ("2|1|3|2|1", "operaciones"), ("2|1|3|1|2", "wishlist")])
    def test_un_recuento_distinto_tras_restaurar_recupera_la_copia_previa(self, tmp_path, cuentas, tabla):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DB_COUNTS": cuentas})
        assert r.returncode != 0
        assert f"recuento distinto en {tabla}" in r.stderr
        assert "seguridad" in _log(ctx, "restore")                         # y recuperó la copia previa
        assert "Datos restaurados" not in r.stdout

    @pytest.mark.parametrize("huerfanos,campo", [
        ("1|0|0|0", "files=1"), ("0|1|0|0", "issues=1"), ("0|0|1|0", "wishlist=1"), ("0|0|0|1", "operaciones=1")])
    def test_los_vinculos_huerfanos_recuperan_la_copia_previa(self, tmp_path, huerfanos, campo):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DB_ORPHANS": huerfanos})
        assert r.returncode != 0
        assert "vínculos huérfanos" in r.stderr and campo in r.stderr
        assert "seguridad" in _log(ctx, "restore") and "Datos restaurados" not in r.stdout

    def test_un_health_200_con_la_base_en_error_no_vale(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_HEALTH": "db_error", "HEALTH_TIMEOUT": "1", "HEALTH_INTERVAL": "1"})
        assert r.returncode != 0 and "database=ok" in r.stderr
        assert "seguridad" in _log(ctx, "restore")

    def test_una_copia_previa_que_no_pasa_gzip_t_aborta_sin_tocar_la_bd(self, tmp_path):
        ctx = _preparar(tmp_path)
        gz = ctx["bin"] / "gzip"
        gz.write_text(GZIP_QUE_FALLA_EN_LA_COPIA_PREVIA, encoding="utf-8")
        gz.chmod(0o755)
        r = _ejecutar(ctx, extra_env={"REAL_GZIP": shutil.which("gzip") or "/usr/bin/gzip"})
        assert r.returncode != 0 and "no pasa gzip -t" in r.stderr
        stub = _log(ctx, "stub")
        assert "dropdb" not in stub and " stop " not in stub and "createdb" not in stub   # la BD no se tocó
        assert not list(ctx["backup"].glob("rollback-safety_*.sql.gz"))


GZIP_QUE_ANOTA_EL_MODO = """#!/usr/bin/env bash
# Anota el modo del fichero al que escribe gzip (su stdout) en el momento de empezar a volcar.
if [[ "$1" != "-t" && "$1" != "-dc" && "$1" != "-l" ]]; then
    stat -L -c '%a' /proc/$$/fd/1 >> "${MODO_LOG:?}" 2>/dev/null || true
fi
exec "${REAL_GZIP:?}" "$@"
"""


class TestCorreccionesDeSecOps:
    """#123 (SecOps sobre #376): R-2 (recuperar si el dropdb falla), R-3 (temporal 600) y R-4 (mensajes limpios)."""

    def test_si_falla_al_eliminar_la_bd_se_intenta_recuperar_la_copia_previa(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DROP_FAIL": "1"})
        assert r.returncode != 0
        assert "el dropdb falló: la BD debería seguir como estaba" in r.stderr and "Intentando recuperar la BD anterior" in r.stderr

    def test_la_copia_previa_nace_600_no_644(self, tmp_path):
        ctx = _preparar(tmp_path)
        modos = tmp_path / "modos.log"
        modos.write_text("", encoding="utf-8")
        gz = ctx["bin"] / "gzip"
        gz.write_text(GZIP_QUE_ANOTA_EL_MODO, encoding="utf-8")
        gz.chmod(0o755)
        r = _ejecutar(ctx, extra_env={"REAL_GZIP": shutil.which("gzip") or "/usr/bin/gzip", "MODO_LOG": str(modos)})
        assert r.returncode == 0, r.stdout + r.stderr
        anotados = modos.read_text(encoding="utf-8").split()
        assert anotados and set(anotados) == {"600"}, anotados            # durante TODO el pg_dump, no solo al final

    @pytest.mark.parametrize("donde", ["dump", "manifiesto"])
    def test_una_revision_con_caracteres_de_control_no_llega_al_mensaje(self, tmp_path, donde):
        sucio = "0099\x1b[31m;$(id)`x`"
        if donde == "dump":
            ctx = _preparar(tmp_path, sql=_sql(alembic=sucio))
        else:
            ctx = _preparar(tmp_path)
            datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
            datos["alembic"] = sucio
            ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0
        assert "\x1b" not in r.stderr and "$(" not in r.stderr and "`" not in r.stderr
        assert "0099" in r.stderr                                          # sigue diciendo de qué revisión se trata


class TestMensajesLimpiosYComparacionCruda:
    """#123 (SecOps H-A, H-B): lo que viene del dump, del manifiesto o de la BD se compara CRUDO y se limpia solo para mostrar."""

    ESC = "\x1b[7mXX"

    def test_h_b_una_revision_con_un_caracter_de_control_no_se_hace_pasar_por_otra(self, tmp_path):
        ctx = _preparar(tmp_path, sql=_sql(alembic="0019"))
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["alembic"] = "00\x0119"                                   # limpiado sería 0019 y pasaría la comprobación
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx, extra_env={"FAKE_DB_ALEMBIC": "0019"})
        assert r.returncode != 0
        assert "dropdb" not in _log(ctx, "stub") and "createdb" not in _log(ctx, "stub")   # y se para ANTES de tocar la BD

    def test_h_a_la_revision_actual_con_escapes_no_llega_al_mensaje(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DB_ALEMBIC": "0020" + self.ESC})
        assert r.returncode != 0 and "La BD actual está en" in r.stderr
        assert "[7m" not in r.stderr and "0020" in r.stderr

    def test_h_a_el_schema_del_manifiesto_con_escapes_no_llega_al_mensaje(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["schema"] = "2" + self.ESC
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0 and "declara schema" in r.stderr
        assert "[7m" not in r.stderr and "'2" in r.stderr

    def test_h_a_la_revision_restaurada_con_escapes_no_llega_al_mensaje(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DB_ALEMBIC_POST": "0021" + self.ESC})
        assert r.returncode != 0 and "la revisión restaurada es" in r.stderr
        assert "[7m" not in r.stderr and "0021" in r.stderr

    def test_h_a_el_nombre_del_dump_con_escapes_no_llega_al_resumen(self, tmp_path):
        ctx = _preparar(tmp_path)
        nuevo = ctx["dump"].with_name("update_20261029_210527" + self.ESC + ".sql.gz")
        ctx["dump"].rename(nuevo)
        sidecar = ctx["dump"].with_name(ctx["dump"].name + ".sha256")
        if sidecar.exists():
            sidecar.unlink()
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["backup"] = nuevo.name
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx, args=["--dump", str(nuevo), "--manifest", str(ctx["manifest"]),
                                 "--sha", ctx["head"], "--yes"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "[7m" not in r.stdout + r.stderr


GIT_QUE_CAMBIA_EL_HEAD = """#!/usr/bin/env bash
# La primera lectura de HEAD es la real; las siguientes devuelven otro commit (el HEAD «cambió durante la restauración»).
if [[ "$*" == *"rev-parse HEAD"* ]]; then
    if [[ -f "${HEAD_VISTO:?}" ]]; then echo "ffffffffffffffffffffffffffffffffffffffff"; exit 0; fi
    : > "$HEAD_VISTO"
fi
exec "${REAL_GIT:?}" "$@"
"""


class TestMasGuardasDeLaRestauracion:
    """#123 (QA, A2 de #376): guardas que sobrevivían a la mutación."""

    def test_la_bd_actual_en_otra_revision_que_la_esperada_no_se_toca(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, extra_env={"FAKE_DB_ALEMBIC": "0019"})            # el dump y el manifiesto dicen 0020
        assert r.returncode != 0 and "La BD actual está en '0019'" in r.stderr
        assert "dropdb" not in _log(ctx, "stub") and "createdb" not in _log(ctx, "stub")

    def test_un_dump_de_otra_revision_que_la_esperada_no_se_restaura(self, tmp_path):
        ctx = _preparar(tmp_path)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos.pop("alembic")                                               # sin esto otra guarda saltaría antes
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        args = ["--dump", str(ctx["dump"]), "--manifest", str(ctx["manifest"]), "--sha", ctx["head"],
                "--alembic-esperada", "0021", "--yes"]
        r = _ejecutar(ctx, args=args)
        assert r.returncode != 0 and "Revisión incompatible: dump '0020', esperada '0021'" in r.stderr
        assert "dropdb" not in _log(ctx, "stub")

    def test_si_el_head_cambia_durante_la_restauracion_se_recupera_la_copia_previa(self, tmp_path):
        ctx = _preparar(tmp_path)
        git = ctx["bin"] / "git"
        git.write_text(GIT_QUE_CAMBIA_EL_HEAD, encoding="utf-8")
        git.chmod(0o755)
        r = _ejecutar(ctx, extra_env={"HEAD_VISTO": str(tmp_path / "head-visto")})
        assert r.returncode != 0 and "el HEAD cambió durante la restauración" in r.stderr
        assert "seguridad" in _log(ctx, "restore")

    def test_una_copia_previa_que_no_es_una_bd_de_zascarr_aborta_sin_tocar_la_bd(self, tmp_path):
        ctx = _preparar(tmp_path)
        ctx["safety_sql"].write_text("--\n-- PostgreSQL database dump\n--\nCREATE TABLE public.otra (id integer);\n",
                                     encoding="utf-8")
        r = _ejecutar(ctx)
        assert r.returncode != 0 and "no parece una BD de ZascArr" in r.stderr
        stub = _log(ctx, "stub")
        assert "dropdb" not in stub and "createdb" not in stub and not list(ctx["backup"].glob("rollback-safety_*.sql.gz"))


    def test_n_1_el_manifiesto_y_la_revision_esperada_del_resumen_salen_limpios(self, tmp_path):
        """Sin --manifest el nombre del manifiesto sale del nombre del dump (con escapes): no llega crudo al resumen."""
        esc = "\x1b[7mXX"
        ctx = _preparar(tmp_path)
        nuevo = ctx["dump"].with_name("update_20261029_210527" + esc + ".sql.gz")
        ctx["dump"].rename(nuevo)
        ctx["manifest"].rename(ctx["backup"] / ("MANIFIESTO-update_20261029_210527" + esc + ".json"))
        viejo = ctx["dump"].with_name(ctx["dump"].name + ".sha256")
        if viejo.exists():
            viejo.unlink()
        r = _ejecutar(ctx, args=["--dump", str(nuevo), "--sha", ctx["head"], "--yes"])
        assert r.returncode == 0, r.stdout + r.stderr
        assert "[7m" not in r.stdout + r.stderr and "Manifiesto:" in r.stdout

    def test_n_1_la_revision_esperada_con_escapes_sale_limpia_en_el_resumen(self, tmp_path):
        esc = "\x1b[7mXX"
        ctx = _preparar(tmp_path, sql=_sql(alembic="0020" + esc))
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos.pop("alembic")
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(ctx, extra_env={"FAKE_DB_ALEMBIC": "0020" + esc})
        assert r.returncode == 0, r.stdout + r.stderr
        assert "Alembic esperado:" in r.stdout and "[7m" not in r.stdout + r.stderr


    def test_el_dump_inexistente_con_escapes_en_el_nombre_sale_limpio(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, args=["--dump", str(ctx["backup"] / ("no-existe\x1b[7mXX.sql.gz")),
                                 "--sha", ctx["head"], "--yes"])
        assert r.returncode != 0 and "El dump no existe o está vacío" in r.stderr
        assert "[7m" not in r.stderr and "no-existe" in r.stderr

    def test_el_manifiesto_ausente_con_un_dump_de_nombre_con_escapes_sale_limpio(self, tmp_path):
        ctx = _preparar(tmp_path)
        nuevo = ctx["dump"].with_name("update_20261029_210527\x1b[7mXX.sql.gz")
        ctx["dump"].rename(nuevo)                       # y no hay MANIFIESTO-<ese nombre>.json
        r = _ejecutar(ctx, args=["--dump", str(nuevo), "--sha", ctx["head"], "--yes"])
        assert r.returncode != 0 and "No encuentro el manifiesto" in r.stderr
        assert "[7m" not in r.stderr and "MANIFIESTO-update_20261029_210527" in r.stderr
