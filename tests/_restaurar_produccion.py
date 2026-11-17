# ruff: noqa: E501
"""Arnés de las pruebas del flujo `restaurar_datos.sh --produccion` (BL-OPS2, F-03/F-04).

El script se ejecuta tal cual, con un `docker` falso en PATH que simula un proyecto Compose (`postgres` +
`zascarr`) y varias bases de datos en ficheros dentro de `$FAKE_ESTADO_DIR`:

- `config` devuelve el proyecto Compose.
- `createdb`/`dropdb` crean/borran `db.<nombre>`; `ALTER DATABASE ... RENAME` renombra el fichero.
- `psql -c` contesta a las consultas que hace el script (seguridad, recuentos genéricos, alembic, pg_database,
  huérfanos); por entrada estándar registra el dump cargado y extrae la fila `runtime_settings` reaplicada.
- `pg_dump` exige que la app esté parada cuando `FAKE_ENFORCE_STOP=1` (F-04), igual que la relectura de seguridad.
- `stop`/`up -d` marcan/desmarcan `app_parada`.

No se necesita PostgreSQL real: el contrato que se prueba es el ORDEN de las operaciones, qué base se toca en cada
fallo, el estado `ops-restaurar.json` y que la base viva no se destruya antes de tiempo. La prueba con PostgreSQL
real (T-10/T-21) vive aparte.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "restaurar_datos.sh"

DOCKER_FALSO = r"""#!/usr/bin/env bash
set -uo pipefail
printf '%s\n' "docker $*" >> "$FAKE_LOG"
evento() { printf '%s\n' "$*" >> "$FAKE_EVENTOS"; }
app_parada() { [[ -f "$FAKE_ESTADO_DIR/app_parada" ]]; }
fallo_orden() { evento "VIOLACION: $*"; exit 9; }

if [[ "${1:-}" != "compose" ]]; then
    exit 0
fi
shift
sub=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--env-file|-p|--project-name) shift 2 ;;
        config|exec|stop|up|down|ps|logs) sub="$1"; shift; break ;;
        *) shift ;;
    esac
done
case "$sub" in
    config) cat "$FAKE_COMPOSE_JSON"; exit 0 ;;
    stop)
        if [[ "${1:-}" == "zascarr" ]]; then
            : > "$FAKE_ESTADO_DIR/app_parada"
            evento "stop zascarr"
        fi
        exit 0 ;;
    up)
        if [[ " $* " == *" zascarr "* ]]; then
            rm -f "$FAKE_ESTADO_DIR/app_parada"
            evento "up zascarr"
        fi
        exit 0 ;;
    exec) : ;;
    *) exit 0 ;;
esac
[[ "${1:-}" == "-T" ]] && shift
servicio="${1:-}"; shift || true
cmd="${1:-}"; shift || true
case "$cmd" in
    df)
        printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
        printf '/ %s 1 %s 1%% /\n' "${FAKE_PG_FREE_KB:-99999999}" "${FAKE_PG_FREE_KB:-99999999}"
        exit 0 ;;
    pg_database_size) echo "${FAKE_DB_SIZE_KB:-1024}"; exit 0 ;;
    createdb)
        if [[ "${FAKE_CREATEDB_FAIL:-0}" == "1" ]]; then echo "createdb: boom" >&2; exit 1; fi
        db="${*: -1}"
        touch "$FAKE_ESTADO_DIR/db.$db"
        evento "createdb $db"
        exit 0 ;;
    dropdb)
        if [[ "${FAKE_DROP_FAIL:-0}" == "1" ]]; then echo "dropdb: boom" >&2; exit 1; fi
        db="${*: -1}"
        rm -f "$FAKE_ESTADO_DIR/db.$db"
        evento "dropdb $db"
        exit 0 ;;
    pg_dump)
        db="${*: -1}"
        if [[ "${FAKE_ENFORCE_STOP:-0}" == "1" ]] && ! app_parada; then
            fallo_orden "pg_dump con la app sirviendo"
        fi
        evento "pg_dump $db"
        cat "$FAKE_DB_DUMP_SQL"
        exit 0 ;;
    psql) : ;;
    *) exit 0 ;;
esac
# ── psql ────────────────────────────────────────────────────────────────────────────────────────────────────────
db=""; sql=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        -U) shift 2 ;;
        -d) db="$2"; shift 2 ;;
        -c) sql="$2"; shift 2 ;;
        -At|-q|-t|-A) shift ;;
        -v) shift 2 ;;
        *) shift ;;
    esac
done
if [[ -z "$sql" ]]; then
    payload="$(cat)"
    printf '%s\n' "$payload" >> "$FAKE_RESTORE_LOG"
    if [[ "$payload" == *"INSERT INTO runtime_settings"* ]]; then
        if [[ "${FAKE_INSERT_FAIL:-0}" == "1" ]]; then
            evento "reaplicar_seguridad_fallida"
            echo "invalid input syntax for type json" >&2
            exit 1
        fi
        # Extrae el literal entre comillas de dólar y guárdalo como fila resultante de la base nueva.
        printf '%s' "$payload" > "$FAKE_ESTADO_DIR/insert.sql"
        python3 - "$FAKE_ESTADO_DIR/insert.sql" "$FAKE_ESTADO_DIR/seg_nueva.json" <<'PYEOF'
import re
import sys

datos = open(sys.argv[1], encoding="utf-8").read()
encontrado = re.search(r"\$([A-Za-z0-9_]+)\$(.*?)\$\1\$::jsonb", datos, re.S)
open(sys.argv[2], "w", encoding="utf-8").write(encontrado.group(2) if encontrado else "")
PYEOF
        evento "reaplicar_seguridad"
    fi
    if [[ "${FAKE_RESTORE_FAIL:-0}" == "1" ]]; then
        if [[ ! -f "$FAKE_ESTADO_DIR/restore_fallo.marker" ]]; then
            : > "$FAKE_ESTADO_DIR/restore_fallo.marker"
            echo "restore: boom" >&2
            exit 1
        fi
    fi
    exit 0
fi
case "$sql" in
    ALTER\ DATABASE*)
        desde="$(printf '%s' "$sql" | sed -n 's/.*ALTER DATABASE "\([^"]*\)" RENAME TO "\([^"]*\)".*/\1/p')"
        hasta="$(printf '%s' "$sql" | sed -n 's/.*ALTER DATABASE "\([^"]*\)" RENAME TO "\([^"]*\)".*/\2/p')"
        if [[ ",${FAKE_RENAME_FAIL:-}," == *",$desde>$hasta,"* ]]; then
            evento "renombrar_fallido $desde>$hasta"
            echo "ALTER DATABASE: other users" >&2
            exit 1
        fi
        if [[ -f "$FAKE_ESTADO_DIR/db.$desde" ]]; then
            mv "$FAKE_ESTADO_DIR/db.$desde" "$FAKE_ESTADO_DIR/db.$hasta"
        fi
        if [[ "${FAKE_OCULTA_PREVIA:-0}" == "1" && "$hasta" == "zascarr_previa" ]]; then
            rm -f "$FAKE_ESTADO_DIR/db.zascarr_previa"
        fi
        evento "renombrar $desde>$hasta"
        exit 0 ;;
    *pg_database_size*) echo "${FAKE_DB_SIZE_KB:-1024}"; exit 0 ;;
    *"from pg_database"*)
        nombre="$(printf '%s' "$sql" | sed -n "s/.*datname *= *'\([^']*\)'.*/\1/p")"
        [[ -f "$FAKE_ESTADO_DIR/db.$nombre" ]] && echo 1 || echo ""
        exit 0 ;;
    *"select version_num from alembic_version"*)
        echo "${FAKE_ALEMBIC:-0020}"; exit 0 ;;
    *"left join"*)
        echo "${FAKE_ORPHANS:-0|0|0|0}"; exit 0 ;;
    *"select values::text from runtime_settings"*)
        case "$db" in
            *restaurando)
                if [[ -f "$FAKE_ESTADO_DIR/seg_nueva.json" ]]; then
                    cat "$FAKE_ESTADO_DIR/seg_nueva.json"
                else
                    cat "$FAKE_SEG_COPIA"
                fi ;;
            *)
                # La precondición de FR-18 se lee con la app sirviendo (antes de crear la base nueva); la
                # relectura autoritativa de FR-20.6, después de pararla.
                if [[ "${FAKE_ENFORCE_STOP:-0}" == "1" ]] && ! app_parada \
                        && [[ -f "$FAKE_ESTADO_DIR/db.zascarr_restaurando" ]]; then
                    fallo_orden "seguridad vigente leída con la app sirviendo"
                fi
                cat "$FAKE_SEG_ACTUAL" ;;
        esac
        exit 0 ;;
    *"count(*)"*)
        tabla="$(printf '%s' "$sql" | sed -n 's/.*from "\([^"]*\)".*/\1/p')"
        if [[ -z "$tabla" ]]; then
            tabla="$(printf '%s' "$sql" | sed -n 's/.*from \([a-zA-Z0-9_]*\).*/\1/p')"
        fi
        variable="FAKE_COUNT_${tabla}"
        valor="${!variable:-}"
        if [[ -z "$valor" ]]; then
            for par in ${FAKE_COUNTS:-}; do
                if [[ "${par%%=*}" == "$tabla" ]]; then valor="${par#*=}"; fi
            done
        fi
        if [[ -z "$valor" && "$tabla" == "alembic_version" ]]; then valor=1; fi
        echo "${valor:-0}"
        exit 0 ;;
    *"pg_database_size"*)
        echo "${FAKE_DB_SIZE_KB:-1024}"; exit 0 ;;
    *)
        exit 0 ;;
esac
"""

CURL_FALSO = """#!/usr/bin/env bash
set -uo pipefail
printf '%s\n' "curl $*" >> "$CURL_LOG"
if [[ "${FAKE_HEALTH_FALLS:-0}" != "0" ]]; then
    n=0
    [[ -f "$FAKE_ESTADO_DIR/health.contador" ]] && n=$(cat "$FAKE_ESTADO_DIR/health.contador")
    n=$((n + 1))
    echo "$n" > "$FAKE_ESTADO_DIR/health.contador"
    if (( n <= FAKE_HEALTH_FALLS )); then
        exit 22
    fi
fi
echo '{"status":"healthy","checks":{"database":"ok"}}'
exit 0
"""

GIT_FALSO = """#!/usr/bin/env bash
set -uo pipefail
printf '%s\n' "git $*" >> "$GIT_LOG"
exec "${REAL_GIT:?}" "$@"
"""


def sql_dump(
    *,
    series: int = 2,
    issues: int = 1,
    files: int = 3,
    operaciones: int = 1,
    wishlist: int = 1,
    extra: dict[str, int] | None = None,
    alembic: str = "0020",
    marca: str = "destino",
) -> str:
    """Un dump mínimo con los bloques COPY que el script inspecciona (y los extra que pida la prueba)."""
    lineas = ["--", "-- PostgreSQL database dump", f"-- {marca}", "--"]
    tablas = {
        "alembic_version": None,
        "series": series,
        "issues": issues,
        "files": files,
        "vinculacion_operaciones": operaciones,
        "wishlist": wishlist,
        **(extra or {}),
    }
    for tabla in tablas:
        lineas.append(f"CREATE TABLE public.{tabla} (id integer);")
    lineas += ["COPY public.alembic_version (version_num) FROM stdin;", alembic, "\\."]
    for tabla, n in tablas.items():
        if n is None:
            continue
        lineas.append(f"COPY public.{tabla} (id) FROM stdin;")
        lineas += [str(i) for i in range(n)]
        lineas.append("\\.")
    return "\n".join(lineas) + "\n"


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def preparar(
    tmp_path: Path,
    *,
    sql: str | None = None,
    compose_name: str = "zascarr",
    seguridad_actual: dict | None = None,
    seguridad_copia: dict | None = None,
    counts: dict[str, int] | None = None,
) -> dict:
    """Contexto de una restauración de producción: repo limpio, copia con manifiesto, proyecto Compose y bin falsos."""
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
    compose.write_text(f"name: {compose_name}\n", encoding="utf-8")
    backup = root / "backup"
    backup.mkdir()
    status = root / "status"
    status.mkdir()
    estado_dir = tmp_path / "estado-docker"
    estado_dir.mkdir()

    ts = "20260101_120000"
    dump = backup / f"backup_{ts}.sql.gz"
    dump.write_bytes(gzip.compress((sql or sql_dump()).encode("utf-8")))
    manifest = backup / f"MANIFIESTO-backup_{ts}.json"
    manifest.write_text(json.dumps({
        "schema": 1,
        "backup": dump.name,
        "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
        "bytes": dump.stat().st_size,
        "codigo_destino_sha_completo": head,
        "codigo_desplegado_sha_completo": head,
        "alembic": "0020",
        "created_at": "2026-11-17T10:00:00+01:00",
        "origin": "test",
        "id": "test-1",
    }), encoding="utf-8")

    actual = seguridad_actual or {
        "auth_mode": "password", "auth_username": "ana", "auth_password_hash": "hash-nuevo",
        "secret_key": "sk-nueva", "base_url": "https://nuevo", "auth_session_version": 7,
        "comicvine_enabled": False, "webhook_url": "https://webhook-nuevo",
        "prowlarr_api_key": "clave-vigente", "fuentes_heredadas": False,
    }
    copia = seguridad_copia or {
        "auth_mode": "none", "auth_username": "viejo", "auth_password_hash": "hash-viejo",
        "secret_key": "sk-vieja", "base_url": "https://viejo", "auth_session_version": 3,
        "comicvine_enabled": True, "webhook_url": "https://webhook-viejo",
        "prowlarr_api_key": "clave-copia", "fuentes_heredadas": True,
    }
    seg_actual = tmp_path / "seg-actual.json"
    seg_actual.write_text(json.dumps(actual), encoding="utf-8")
    seg_copia = tmp_path / "seg-copia.json"
    seg_copia.write_text(json.dumps(copia), encoding="utf-8")

    seguridad_sql = tmp_path / "seguridad.sql"
    seguridad_sql.write_text(sql_dump(marca="seguridad"), encoding="utf-8")
    compose_json = tmp_path / "compose.json"
    compose_json.write_text(json.dumps({"name": compose_name, "services": {
        "postgres": {"container_name": "zascarr-db"},
        "zascarr": {"container_name": "zascarr-orquestador"}}}), encoding="utf-8")

    bin_ = tmp_path / "bin"
    bin_.mkdir()
    for nombre, contenido in (("docker", DOCKER_FALSO), ("curl", CURL_FALSO), ("git", GIT_FALSO)):
        ruta = bin_ / nombre
        ruta.write_text(contenido, encoding="utf-8")
        ruta.chmod(0o755)

    contadores = {
        "stub": tmp_path / "stub.log",
        "restore": tmp_path / "restore.log",
        "curl": tmp_path / "curl.log",
        "git": tmp_path / "git.log",
        "eventos": tmp_path / "eventos.log",
    }
    for ruta in contadores.values():
        ruta.write_text("", encoding="utf-8")

    # La base viva existe; `zascarr_restaurando`, `zascarr_previa` y `zascarr_fallida`, no.
    for nombre in ("postgres", "zascarr"):
        (estado_dir / f"db.{nombre}").write_text("", encoding="utf-8")

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
        "ts": ts,
        "seguridad_sql": seguridad_sql,
        "seg_actual": seg_actual,
        "seg_copia": seg_copia,
        "compose_json": compose_json,
        "bin": bin_,
        "estado_docker": estado_dir,
        "counts": counts or {"series": 2, "issues": 1, "files": 3,
                             "vinculacion_operaciones": 1, "wishlist": 1},
        **contadores,
    }


def ejecutar(
    ctx: dict,
    *,
    args: list[str] | None = None,
    extra_env: dict | None = None,
    timeout: int = 90,
    entorno_limpio: bool = False,
) -> subprocess.CompletedProcess:
    env = ({} if entorno_limpio else os.environ.copy())
    env.update({
        "PATH": f"{ctx['bin']}:{os.environ.get('PATH', '/usr/bin:/bin')}",
        "HOME": os.environ.get("HOME", "/tmp"),
        "REAL_GIT": shutil.which("git") or "/usr/bin/git",
        "REPO_DIR": str(ctx["repo"]),
        "ENV_FILE": str(ctx["env"]),
        "COMPOSE_FILE": str(ctx["compose"]),
        "BACKUP_DIR": str(ctx["backup"]),
        "BACKUP_STATUS_DIR": str(ctx["status"]),
        "DB_NAME": "zascarr",
        "DB_USER": "comics_admin",
        "HEALTH_URL": "http://127.0.0.1:18000/api/health",
        "HEALTH_TIMEOUT": "5",
        "HEALTH_INTERVAL": "1",
        "ZASCARR_PRUEBAS": "1",
        "OPS_LOCK_FILE": str(ctx["root"] / "ops.lock"),
        "FAKE_LOG": str(ctx["stub"]),
        "FAKE_EVENTOS": str(ctx["eventos"]),
        "FAKE_RESTORE_LOG": str(ctx["restore"]),
        "FAKE_ESTADO_DIR": str(ctx["estado_docker"]),
        "FAKE_COMPOSE_JSON": str(ctx["compose_json"]),
        "FAKE_DB_DUMP_SQL": str(ctx["seguridad_sql"]),
        "FAKE_SEG_ACTUAL": str(ctx["seg_actual"]),
        "FAKE_SEG_COPIA": str(ctx["seg_copia"]),
        "FAKE_COUNTS": " ".join(f"{k}={v}" for k, v in ctx["counts"].items()),
        "FAKE_ALEMBIC": "0020",
        "CURL_LOG": str(ctx["curl"]),
        "GIT_LOG": str(ctx["git"]),
    })
    if extra_env:
        env.update(extra_env)
    if args is None:
        args = ["--produccion", "--copia", ctx["ts"]]
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        env=env, capture_output=True, text=True, timeout=timeout,
        stdin=subprocess.DEVNULL,
    )


def eventos(ctx: dict) -> list[str]:
    return [linea for linea in ctx["eventos"].read_text(encoding="utf-8").splitlines() if linea]


def estado_restaurar(ctx: dict) -> dict | None:
    ruta = ctx["status"] / "ops-restaurar.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def plantilla_eventos(ctx: dict, *nombres: str) -> list[str]:
    """Solo los eventos cuyo prefijo está en `nombres`, en orden."""
    return [e for e in eventos(ctx) if e.split(" ", 1)[0] in nombres]
