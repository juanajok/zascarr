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
import secrets
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
  *"createdb"*)
    if [[ "${FAKE_CREATEDB_FAIL:-0}" == "1" ]]; then
      echo "${FAKE_CREATEDB_MSG:-createdb: error}" >&2
      exit 1
    fi
    echo "createdb $*" >> "$DB_LOG"
    exit 0 ;;
  *"dropdb"*) echo "dropdb $*" >> "$DB_LOG"; exit 0 ;;
  *"psql"*)
    if [[ "$*" == *" -c "* ]]; then
      if [[ "${FAKE_PSQL_QUERY_FAIL:-0}" == "1" ]]; then
        echo "${FAKE_PSQL_QUERY_MSG:-boom}" >&2
        exit 1
      fi
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
    if [[ "${FAKE_VERBOSE_DUMP:-0}" == "1" ]]; then
      entrada="$(cat)"
      if [[ "$entrada" == *"VERBOSITY verbose"* ]]; then
        printf 'ERROR:  fallo al restaurar\n' >&2
        printf 'CONTEXT:  COPY public.files, line 1: "fila_secreta"\n' >&2
        printf 'LOCATION:  exec_stmt_raise, pl_exec.c:3891\n' >&2
        exit 1
      fi
      printf '%s' "$entrada" > "$RESTORE_LOG"
      exit 0
    fi
    if [[ "${FAKE_PSQL_FAIL:-0}" == "1" ]]; then echo "${FAKE_PSQL_MSG:-boom}" >&2; exit 1; fi
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
    manifest.write_text(
        json.dumps(
            {
                "backup": dump.name,
                "sha256": sha,
                "bytes": bytes_,
                "alembic": "0020",
                "codigo_destino_sha_completo": "a" * 40,
                "codigo_desplegado_sha_completo": "b" * 40,
            }
        ),
        encoding="utf-8",
    )
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
        "repo": repo,
        "root": root,
        "backup": backup,
        "offsite": offsite,
        "status": status,
        "dump": dump,
        "manifest": manifest,
        "bin": bin_,
        "stub": stub,
        "db": db,
        "restore": restore,
    }


def _ejecutar(
    ctx: dict,
    *,
    dump: Path | None = None,
    manifest: Path | None = None,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.update(
        {
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
        }
    )
    if extra_env:
        env.update(extra_env)
    args = ["bash", str(ctx["repo"] / "scripts" / "probar_restauracion.sh")]
    if dump is not None:
        args += ["--dump", str(dump)]
    if manifest is not None:
        args += ["--manifest", str(manifest)]
    return subprocess.run(
        args,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        stdin=subprocess.DEVNULL,
    )


def _estado(ctx: dict) -> dict:
    return json.loads((ctx["status"] / "restore-status.json").read_text(encoding="utf-8"))


def _detalle_en_pantalla(r: subprocess.CompletedProcess, etiqueta: str = "Motivo de psql:") -> str:
    for linea in r.stderr.splitlines():
        if etiqueta in linea:
            return linea.split(etiqueta, 1)[1].strip()
    return ""


def _reescribir_dump(ctx: dict, sql: str) -> None:
    dump = ctx["dump"]
    dump.write_bytes(gzip.compress(sql.encode("utf-8")))
    sha = hashlib.sha256(dump.read_bytes()).hexdigest()
    datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
    datos["sha256"] = sha
    datos["bytes"] = dump.stat().st_size
    ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
    dump.with_name(f"{dump.name}.sha256").write_text(f"{sha}  {dump.name}\n", encoding="utf-8")


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
        assert gzip_t.returncode != 0  # el propio gzip lo ve cortado
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

    def test_tablas_restauradas_raras_no_se_cuelan_en_el_detalle(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "tablas_" + secrets.token_hex(8)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={"FAKE_TABLES": f"28;password={canario}"},
        )
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["error"] == "tablas_distintas"
        assert estado["detalle"] == "dump=28 restaurada=?"
        assert estado["tablas"] == 0
        assert canario not in r.stdout + r.stderr
        assert canario not in json.dumps(estado)

    def test_recuento_restaurado_raro_no_se_cuela_en_el_detalle(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "recuento_" + secrets.token_hex(8)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={"FAKE_FILES": f"3;password={canario}"},
        )
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["error"] == "recuento_distinto"
        assert estado["detalle"] == "files: dump=3 restaurada=?"
        assert estado["recuentos"]["files"] is None
        assert canario not in r.stdout + r.stderr
        assert canario not in json.dumps(estado)

    def test_manifiesto_y_alembic_raros_no_se_cuelan_crudos(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "manifiesto_" + secrets.token_hex(8)
        datos = json.loads(ctx["manifest"].read_text(encoding="utf-8"))
        datos["alembic"] = f"0020;password={canario}\nCONTEXT: {canario}"
        datos["codigo_destino_sha_completo"] = f"a;password={canario}"
        ctx["manifest"].write_text(json.dumps(datos), encoding="utf-8")
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            manifest=ctx["manifest"],
            extra_env={"FAKE_ALEMBIC": "0021"},
        )
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["error"] == "alembic_distinto"
        assert estado["detalle"] == "manifiesto=? restaurada=0021"
        assert estado["alembic"] == "0021"
        assert estado["codigo_destino"] == "?"
        assert canario not in r.stdout + r.stderr
        assert canario not in json.dumps(estado)

    def test_alembic_restaurado_raro_no_se_cuela_en_el_json(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "alembic_" + secrets.token_hex(8)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={"FAKE_ALEMBIC": f"0021;password={canario}"},
        )
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["error"] == "alembic_distinto"
        assert estado["detalle"] == "manifiesto=0020 restaurada=?"
        assert estado["alembic"] == "?"
        assert canario not in r.stdout + r.stderr
        assert canario not in json.dumps(estado)

    def test_psql_roto_falla_y_borra_la_temporal(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, dump=ctx["dump"], extra_env={"FAKE_PSQL_FAIL": "1"})
        assert r.returncode != 0
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "restore_failed"
        assert "dropdb" in ctx["db"].read_text(encoding="utf-8")

    def test_createdb_falla_sanea_stderr_y_lo_guarda(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "createdb_" + secrets.token_hex(8)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_CREATEDB_FAIL": "1",
                "FAKE_CREATEDB_MSG": (
                    f"ERROR:  no se pudo crear password={canario}\n"
                    f'CONTEXT:  COPY public.files, line 1: "{canario}"'
                ),
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        estado = _estado(ctx)
        assert estado["status"] == "failed"
        assert estado["error"] == "createdb_failed"
        assert canario not in salida and canario not in json.dumps(estado)
        assert "CONTEXT" not in salida
        assert estado["detalle"] == _detalle_en_pantalla(r, "Motivo de createdb:")
        assert estado["detalle"] and "password=***" in estado["detalle"]
        assert "createdb" not in ctx["db"].read_text(encoding="utf-8")

    def test_si_psql_falla_el_motivo_sale_por_pantalla_y_sin_credenciales(self, tmp_path):
        """#334: la CI solo mostraba «La restauración falló»; el motivo (`transaction_timeout`,
        que un servidor 15 no conoce tras un `pg_dump` 18) quedaba en `restore-status.json`.
        Ahora sale por stderr, sin credenciales."""
        ctx = _preparar(tmp_path)
        param = 'unrecognized configuration parameter "transaction_timeout"'
        mensaje = (
            f"ERROR:  {param} "
            "(conexion postgresql://zascarr:hunter2@db:5432/zascarr password=hunter2)"
        )
        r = _ejecutar(
            ctx, dump=ctx["dump"], extra_env={"FAKE_PSQL_FAIL": "1", "FAKE_PSQL_MSG": mensaje}
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert param in salida and "La restauración falló" in salida  # el motivo, a la vista
        assert "hunter2" not in salida  # ni en pantalla...
        assert "hunter2" not in json.dumps(_estado(ctx))  # ...ni en el estado
        assert "postgresql://zascarr:***@db" in salida and "password=***" in salida

    def test_solo_error_sobrevive_y_context_no_filtra_datos(self, tmp_path):
        ctx = _preparar(tmp_path)
        # Sin `password=` en la línea ERROR para que el enmascarado no pueda ocultar
        # el CONTEXT/DETAIL: así la prueba distingue de verdad la lista permitida.
        mensaje = (
            "  ERROR:  fallo al restaurar postgresql://zascarr:hunter2@db:5432/zascarr\n"
            'CONTEXT:  COPY public.files, line 1: "hunter2"\n'
            "DETAIL:  Key (id)=(hunter2) already exists.\n"
            "LINE 1: INSERT INTO files VALUES ('hunter2')\n"
            "STATEMENT:  COPY files FROM stdin\n"
            "HINT:  revisa hunter2\n"
            "QUERY:  select * from files where password='hunter2'"
        )
        r = _ejecutar(
            ctx, dump=ctx["dump"], extra_env={"FAKE_PSQL_FAIL": "1", "FAKE_PSQL_MSG": mensaje}
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert "ERROR:" in salida and "hunter2" not in salida
        for etiqueta in ("CONTEXT", "DETAIL", "LINE 1", "STATEMENT", "HINT", "QUERY"):
            assert etiqueta not in salida
        assert "postgresql://zascarr:***@db" in salida
        detalle = _detalle_en_pantalla(r)
        assert detalle and detalle == _estado(ctx)["detalle"]
        assert "hunter2" not in json.dumps(_estado(ctx))

    def test_sin_error_ni_fatal_deja_detalle_null_y_apunta_al_registro(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": (
                    'DETAIL:  Key (id)=(hunter2) already exists.\nCONTEXT: COPY "hunter2"'
                ),
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert "hunter2" not in salida and "hunter2" not in json.dumps(_estado(ctx))
        # `null` distingue «sin detalle» de un texto vacío que parezca éxito.
        assert _estado(ctx)["error"] == "restore_failed"
        assert _estado(ctx)["detalle"] is None
        assert "sin un ERROR/FATAL utilizable" in salida
        assert "revisa el registro" in salida
        assert "La restauración falló." in salida

    def test_panic_tambien_es_una_linea_permitida(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": "PANIC:  el servidor está en apuros",
            },
        )
        assert r.returncode != 0
        assert "PANIC:  el servidor está en apuros" in r.stderr
        assert _detalle_en_pantalla(r) == _estado(ctx)["detalle"]

    def test_fatal_tambien_es_una_linea_permitida(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": "FATAL:  no se pudo conectar",
            },
        )
        assert r.returncode != 0
        assert "FATAL:  no se pudo conectar" in r.stderr

    def test_canario_aleatorio_no_aparece_y_el_error_sigue_legible(self, tmp_path):
        """Invariante: si se redacta todo, se pierde el ERROR; si se filtra, cae el canario."""
        ctx = _preparar(tmp_path)
        canario = "canario_" + secrets.token_hex(12)
        mensaje = (
            f"ERROR:  fallo al restaurar postgresql://u:{canario}@h/db\n"
            f'CONTEXT:  COPY public.files, line 1: "{canario}"\n'
            f"DETAIL:  Key (id)=({canario}) already exists.\n"
            f"STATEMENT:  COPY files FROM stdin -- {canario}\n"
            f"password={canario}&otro={canario}"
        )
        r = _ejecutar(
            ctx, dump=ctx["dump"], extra_env={"FAKE_PSQL_FAIL": "1", "FAKE_PSQL_MSG": mensaje}
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert canario not in salida and canario not in json.dumps(_estado(ctx))
        assert "ERROR:  fallo al restaurar" in salida
        assert "postgresql://u:***@h/db" in salida
        assert _detalle_en_pantalla(r) == _estado(ctx)["detalle"]
        assert "ERROR:  fallo al restaurar" in _estado(ctx)["detalle"]

    def test_cr_no_inyecta_una_linea_y_no_filtra_el_contexto(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "cr_" + secrets.token_hex(8)
        mensaje = f'ERROR:  fallo de prueba\rCONTEXT: COPY t, line 1: "{canario}"'
        r = _ejecutar(
            ctx, dump=ctx["dump"], extra_env={"FAKE_PSQL_FAIL": "1", "FAKE_PSQL_MSG": mensaje}
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert canario not in salida and canario not in json.dumps(_estado(ctx))
        assert "ERROR:  fallo de prueba" in salida
        assert "CONTEXT" not in salida and "DETAIL" not in salida

    def test_el_error_util_sigue_legible(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": 'ERROR:  relation "files" does not exist',
            },
        )
        assert r.returncode != 0
        esperado = 'ERROR:  relation "files" does not exist'
        assert esperado in r.stderr
        assert _estado(ctx)["detalle"] == esperado
        assert _detalle_en_pantalla(r) == esperado

    def test_prefijo_psql_de_fichero_no_publica_la_ruta(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "prefijo_" + secrets.token_hex(8)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": (f"psql:dump.sql:12: ERROR:  fallo de prueba password={canario}"),
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert "dump.sql" not in salida
        assert canario not in salida and canario not in json.dumps(_estado(ctx))
        assert "ERROR:  fallo de prueba" in salida
        assert _detalle_en_pantalla(r) == _estado(ctx)["detalle"]

    def test_psql_usa_verbosity_terse_en_restauracion_y_consultas(self, tmp_path):
        """La primera barrera es el cliente; la allowlist queda como red de seguridad."""
        ctx = _preparar(tmp_path)
        r = _ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"])
        assert r.returncode == 0, r.stdout + r.stderr
        lineas_psql = [
            linea
            for linea in ctx["stub"].read_text(encoding="utf-8").splitlines()
            if " psql " in linea
        ]
        assert lineas_psql
        assert all("VERBOSITY=terse" in linea for linea in lineas_psql), lineas_psql

    def test_un_dump_puede_reactivar_verbose_y_la_allowlist_es_la_garantia(self, tmp_path):
        """`terse` no es infalsificable: un dump con `\\set VERBOSITY verbose` lo revierte."""
        ctx = _preparar(tmp_path)
        _reescribir_dump(ctx, _sql_fixture() + "\\set VERBOSITY verbose\n")
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            manifest=ctx["manifest"],
            extra_env={"FAKE_VERBOSE_DUMP": "1"},
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        estado = _estado(ctx)
        assert "ERROR:  fallo al restaurar" in salida
        for prohibido in ("CONTEXT", "LOCATION", "fila_secreta"):
            assert prohibido not in salida
            assert prohibido not in json.dumps(estado)
        assert estado["detalle"] == "ERROR:  fallo al restaurar"
        # Se pidió terse, pero la garantía frente al dump manipulado es la allowlist.
        assert "VERBOSITY=terse" in ctx["stub"].read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "texto,prohibido,permitido",
        [
            ("postgresql://u:url_secret@host/db", "url_secret", "postgresql://u:***@host/db"),
            (
                "postgresql://u:left@RIGHT@host/db",
                "RIGHT",
                "postgresql://u:***@host/db",
            ),
            ("password=plain_secret", "plain_secret", "password=***"),
            ("password=left@RIGHT", "RIGHT", "password=***"),
            ("password='con espacio'", "con espacio", "password=***"),
            ('password="p@ss@word"', "p@ss@word", "password=***"),
            ('password="left@RIGHT con espacio"', "RIGHT", "password=***"),
            ("passwd=passwd_secret", "passwd_secret", "passwd=***"),
            ("pwd=pwd_secret", "pwd_secret", "pwd=***"),
            ("PGPASSWORD=pg_secret", "pg_secret", "PGPASSWORD=***"),
            ("password=secret&foo=bar", "secret", "password=***"),
            ("password=con espacio", "con espacio", "password=***"),
            ("password=secret)", "secret", "password=***"),
        ],
    )
    def test_variantes_de_credenciales_se_enmascaran(self, tmp_path, texto, prohibido, permitido):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": f"ERROR:  {texto}",
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert prohibido not in salida and prohibido not in json.dumps(_estado(ctx))
        assert permitido in salida

    @pytest.mark.parametrize(
        "plantilla,secreto",
        [
            (plantilla, secreto)
            for plantilla in (
                "postgresql://u:{s}@h/db",
                "PASSWORD='{s}'",
                "PGPASSWORD={s}",
                "password = {s}",
            )
            for secreto in (
                "s3cr3t@",
                "con espacio",
                "apóstrofo'",
                'comilla"',
                "a=b",
                "a&b",
                "100%",
            )
        ],
    )
    def test_tabla_de_secretos_no_filtra_y_conserva_el_error(self, tmp_path, plantilla, secreto):
        ctx = _preparar(tmp_path)
        texto = plantilla.format(s=secreto)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": f"psql:dump.sql:12: ERROR:  fallo de prueba {texto}",
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        estado = _estado(ctx)
        assert secreto not in salida, texto
        assert secreto not in json.dumps(estado), texto
        assert "ERROR:  fallo de prueba" in salida
        assert "dump.sql" not in salida
        assert _detalle_en_pantalla(r) == estado["detalle"]

    def test_un_valor_entre_comillas_con_espacios_no_deja_fragmentos(self, tmp_path):
        """Si solo se enmascara el primer token, el resto del secreto quedaría a la vista."""
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": "ERROR:  conexión con password='alfa beta gamma' rechazada",
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert "password=***" in salida
        assert "alfa" not in salida and "beta" not in salida and "gamma" not in salida
        assert "beta" not in json.dumps(_estado(ctx))

    @pytest.mark.parametrize(
        "texto,prohibido",
        [
            ('password="abc\\"LEAK1"', "LEAK1"),
            ("password='it''sLEAK2'", "LEAK2"),
            ('password="abc\\"LEAK3 con espacio"', "espacio"),
            ("password='it''sLEAK4 con espacio'", "espacio"),
        ],
    )
    def test_comillas_escapadas_exigen_la_regla_final(self, tmp_path, texto, prohibido):
        """La comilla escapada corta la alternativa; la regla final limpia el resto."""
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": f"ERROR:  fallo de prueba {texto}",
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        estado = _estado(ctx)
        assert prohibido not in salida and prohibido not in json.dumps(estado)
        assert "password=***" in salida
        assert "ERROR:  fallo de prueba" in salida
        assert _detalle_en_pantalla(r) == estado["detalle"]

    def test_trunca_despues_de_enmascarar(self, tmp_path):
        ctx = _preparar(tmp_path)
        secreto = "supersecret"
        mensaje = "ERROR:  " + ("x" * 380) + f" password={secreto}" + ("y" * 120)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_FAIL": "1",
                "FAKE_PSQL_MSG": mensaje,
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert secreto not in salida and secreto not in json.dumps(_estado(ctx))
        assert len(_detalle_en_pantalla(r)) <= 400

    def test_no_queda_un_fragmento_del_secreto_al_truncar(self, tmp_path):
        """Si se trunca antes de redactar, un `@` fuera del corte deja medio secreto a la vista."""
        ctx = _preparar(tmp_path)
        secreto = "SECRETO1234567890"
        mensaje = "ERROR:  " + ("x" * 370) + f" postgresql://u:{secreto}@h/db"
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={"FAKE_PSQL_FAIL": "1", "FAKE_PSQL_MSG": mensaje},
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        assert secreto[:6] not in salida
        assert secreto[:6] not in json.dumps(_estado(ctx))
        assert "postgresql://u:***" in salida
        assert len(_detalle_en_pantalla(r)) <= 400

    def test_psql_temp_tambien_sanea_y_no_imprime_crudo(self, tmp_path):
        ctx = _preparar(tmp_path)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_QUERY_FAIL": "1",
                "FAKE_PSQL_QUERY_MSG": (
                    "ERROR:  fallo password=query_secret\nCONTEXT: COPY x\nDETAIL: query_secret"
                ),
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        estado = _estado(ctx)
        assert "query_secret" not in salida and "query_secret" not in json.dumps(estado)
        assert "CONTEXT" not in salida and "DETAIL" not in salida
        assert estado["error"] == "restore_failed"
        assert estado["detalle"] == _detalle_en_pantalla(r)
        assert estado["detalle"] and "query_secret" not in estado["detalle"]

    def test_psql_temp_sin_error_deja_null_y_apunta_al_registro(self, tmp_path):
        ctx = _preparar(tmp_path)
        canario = "query_" + secrets.token_hex(8)
        r = _ejecutar(
            ctx,
            dump=ctx["dump"],
            extra_env={
                "FAKE_PSQL_QUERY_FAIL": "1",
                "FAKE_PSQL_QUERY_MSG": (
                    f'DETAIL:  Key (id)=({canario}) already exists.\nCONTEXT: COPY "{canario}"'
                ),
            },
        )
        assert r.returncode != 0
        salida = r.stdout + r.stderr
        estado = _estado(ctx)
        assert canario not in salida and canario not in json.dumps(estado)
        assert estado["error"] == "restore_failed"
        assert estado["detalle"] is None
        assert "sin un ERROR/FATAL utilizable" in salida
        assert "revisa el registro" in salida

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
