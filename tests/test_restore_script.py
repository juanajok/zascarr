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


@pytest.mark.skipif(sys.platform == "win32", reason="permisos POSIX")
def test_el_script_es_ejecutable():
    """El hook y el wrapper del timer lo ejecutan directamente, no con `bash`."""
    assert os.access(SCRIPTS / "probar_restauracion.sh", os.X_OK)

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
        *"from pg_class"*) echo "${FAKE_TABLES:-28}" ;;
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


def _reescribir_dump(ctx: dict, sql: str) -> None:
    dump = ctx["dump"]
    dump.write_bytes(gzip.compress(sql.encode("utf-8")))
    sha = hashlib.sha256(dump.read_bytes()).hexdigest()
    datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
    datos["sha256"] = sha
    datos["bytes"] = dump.stat().st_size
    ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
    dump.with_name(f"{dump.name}.sha256").write_text(
        f"{sha}  {dump.name}\n", encoding="utf-8"
    )


def _sql_sin_copy(tabla: str) -> str:
    """El dump de prueba sin el bloque `COPY public.<tabla> … \\.` (sigue su `CREATE TABLE`)."""
    salida, dentro = [], False
    for linea in _sql_fixture().splitlines():
        if linea.startswith(f"COPY public.{tabla} "):
            dentro = True
            continue
        if dentro:
            dentro = linea != "\\."
            continue
        salida.append(linea)
    return "\n".join(salida) + "\n"


def _reescribir_bytes(ctx: dict, datos: bytes) -> None:
    """Como `_reescribir_dump`, pero con los bytes tal cual (manifiesto y .sha256 los acreditan)."""
    dump = ctx["dump"]
    dump.write_bytes(datos)
    sha = hashlib.sha256(datos).hexdigest()
    manifiesto = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
    manifiesto["sha256"], manifiesto["bytes"] = sha, len(datos)
    ctx["manifest"].write_text(json.dumps(manifiesto), encoding="utf-8")
    dump.with_name(f"{dump.name}.sha256").write_text(f"{sha}  {dump.name}\n", encoding="utf-8")


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

    def test_dump_grande_no_muere_por_sigpipe(self, tmp_path):
        """Regresión de la ventana: `awk` salía tras la primera fila de
        `alembic_version`; `gzip -dc` recibía SIGPIPE y `pipefail` mataba el
        script con 141 antes de restaurar."""
        ctx = _preparar(tmp_path)
        lineas = _sql_fixture().splitlines()
        lineas += ["COPY public.tabla_00 (id) FROM stdin;"]
        lineas += [str(i) for i in range(200_000)]
        lineas += ["\\."]
        _reescribir_dump(ctx, "\n".join(lineas) + "\n")

        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode == 0, r.stdout + r.stderr
        estado = _estado(ctx)
        assert estado["status"] == "ok"
        assert estado["alembic"] == "0020"

    def test_dump_truncado_no_crea_base(self, tmp_path):
        ctx = _preparar(tmp_path)
        ctx["dump"].write_bytes(b"no es gzip")
        r = _ejecutar(ctx, dump=ctx["dump"])
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "gzip_invalid"
        assert "createdb" not in ctx["db"].read_text(encoding="utf-8")

    @pytest.mark.parametrize("tabla", ["alembic_version", "series", "files", "wishlist"])
    def test_dump_sin_una_tabla_requerida_no_se_restaura(self, tmp_path, tabla):
        """`verificar_dump` exige las cuatro tablas que `rollback.sh` necesita; se prueba cada una
        por separado: con cualquiera ausente el estado es `tables_missing` y no se llega a crear
        la base desechable."""
        ctx = _preparar(tmp_path)
        _reescribir_dump(ctx, _sql_sin_copy(tabla))
        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed" and estado["error"] == "tables_missing"
        assert f"falta la tabla {tabla}" in r.stdout + r.stderr
        assert "createdb" not in ctx["db"].read_text(encoding="utf-8")

    def test_gzip_realmente_truncado_no_crea_base(self, tmp_path):
        """El caso real (disco lleno, copia cortada): un .gz que empezó bien y al que le falta la
        cola. La prueba anterior usa bytes que ni siquiera son gzip. Aquí el manifiesto y el
        .sha256 acreditan el fichero ya cortado, así que solo `gzip -t` puede detenerlo."""
        ctx = _preparar(tmp_path)
        lineas = _sql_fixture().splitlines() + ["COPY public.tabla_00 (id) FROM stdin;"]
        lineas += [str(i) for i in range(50_000)] + ["\\."]
        completo = gzip.compress(("\n".join(lineas) + "\n").encode("utf-8"))
        cortado = completo[: len(completo) // 2]
        assert cortado[:2] == b"\x1f\x8b" and len(cortado) > 1000  # cabecera válida, cuerpo cortado
        gzip_t = subprocess.run(["gzip", "-t"], input=cortado, capture_output=True)
        assert gzip_t.returncode != 0                                 # el propio gzip lo ve cortado
        _reescribir_bytes(ctx, cortado)

        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed" and estado["error"] == "gzip_invalid"
        assert "gzip -t falla" in r.stdout + r.stderr
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
