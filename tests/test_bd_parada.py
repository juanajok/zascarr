# ruff: noqa: E501
"""#123 (corrección tras #385): medir la BD con PostgreSQL PARADO no puede matar el script en silencio.

`tamano_bd_kb` corría dentro de `TAMANO_KB="$(…)"` bajo `set -euo pipefail`: si `docker compose exec … psql` fallaba (BD
parada), el script salía con rc=1 y SIN mensaje, antes de «Levantando PostgreSQL» (rollback) o de «El backup falló»
(update). Además un tamaño no medible se tomaba como 0 y el chequeo de espacio fallaba abierto.

Se reutilizan los arneses de cada script y se envuelve su `docker` falso con uno que reproduce la BD parada:
`exec` falla hasta que se ejecuta `up -d` (modo `hasta_arrancar`), siempre (`siempre`) o solo la consulta del tamaño (`solo_tamano`).
"""
from __future__ import annotations

import gzip
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests import test_backup_script as t_backup
from tests import test_restaurar_datos as t_restaurar
from tests import test_rollback_script as t_rollback
from tests import test_update_manifest as t_update

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")

RAIZ = Path(__file__).resolve().parents[1]
SCRIPTS = RAIZ / "scripts"

ENVOLTURA = r"""#!/usr/bin/env bash
# BD parada: `compose exec` falla mientras no se haya ejecutado `up -d` (hasta_arrancar) o siempre (siempre).
case "$*" in *" up -d"*) touch "${PG_ARRANCADO:?}" ;; esac
if [[ "$*" == *" exec "* ]]; then
    if [[ "${PG_MODO:?}" == "siempre" || ( "${PG_MODO}" == "hasta_arrancar" && ! -f "${PG_ARRANCADO}" ) \
          || ( "${PG_MODO}" == "solo_tamano" && "$*" == *pg_database_size* ) ]]; then
        echo "service \"postgres\" is not running" >&2
        exit 1
    fi
fi
exec "${DOCKER_REAL:?}" "$@"
"""


def _parar_bd(bin_: Path, tmp_path: Path, modo: str) -> dict:
    """Mueve el `docker` falso del arnés y pone la envoltura delante. Devuelve el entorno extra."""
    real = bin_ / "docker_real"
    shutil.move(str(bin_ / "docker"), str(real))
    (bin_ / "docker").write_text(ENVOLTURA, encoding="utf-8")
    (bin_ / "docker").chmod(0o755)
    return {"DOCKER_REAL": str(real), "PG_MODO": modo, "PG_ARRANCADO": str(tmp_path / "pg-arrancado")}


def _salida(r: subprocess.CompletedProcess) -> str:
    return r.stdout + r.stderr


class TestRollback:
    def test_con_postgres_parado_lo_levanta_y_sigue_como_antes(self, tmp_path):
        ctx = t_rollback._preparar(tmp_path)
        t_rollback._manifest(ctx)
        extra = _parar_bd(ctx["bin"], tmp_path, "hasta_arrancar")
        r = t_rollback._ejecutar(ctx, extra_env=extra)
        assert "Levantando PostgreSQL" in _salida(r)                     # ya no sale mudo antes de llegar aquí
        assert "No pude medir" not in _salida(r) and r.returncode == 0, _salida(r)
        assert list(ctx["backup"].glob("rollback-safety_*.sql.gz"))      # y hizo su copia de seguridad

    def test_si_aun_arriba_no_se_puede_medir_dice_por_que_y_no_toca_nada(self, tmp_path):
        ctx = t_rollback._preparar(tmp_path)
        t_rollback._manifest(ctx)
        extra = _parar_bd(ctx["bin"], tmp_path, "solo_tamano")
        r = t_rollback._ejecutar(ctx, extra_env=extra)
        assert r.returncode != 0
        assert "No pude medir" in _salida(r)                              # con mensaje, no mudo
        t_rollback._no_destructivo(ctx)

    def test_con_la_bd_en_marcha_no_cambia(self, tmp_path):
        ctx = t_rollback._preparar(tmp_path)
        t_rollback._manifest(ctx)
        r = t_rollback._ejecutar(ctx)
        assert r.returncode == 0, _salida(r)
        assert "No pude medir" not in _salida(r)


class TestUpdate:
    def test_con_postgres_parado_dice_que_no_pudo_comprobar_y_no_deja_referencia(self, tmp_path):
        repo, _raiz, bin_, log, entorno, prev, _nuevo, fixture = t_update._preparar(tmp_path)
        extra = _parar_bd(bin_, tmp_path, "siempre")
        backup = tmp_path / "backups"
        r = subprocess.run(
            ["bash", str(repo / "scripts" / "update.sh"), "--rama", "main"],
            capture_output=True, text=True, timeout=180, check=False, stdin=subprocess.DEVNULL,
            env={**entorno, "PATH": f"{bin_}:{entorno['PATH']}", "STUB_LOG": str(log), "FIXTURE_SQL": str(fixture),
                 "BACKUP_DIR": str(backup), "HEALTH_TIMEOUT": "2", "BRANCH": "main", **extra})
        assert r.returncode != 0
        assert "No pude comprobar" in _salida(r) and "NO se ha actualizado nada" in _salida(r)
        refs = t_update._git(repo, "for-each-ref", "refs/zascarr/update", env=entorno).stdout.strip()
        assert refs == ""                                                  # nada hecho: no queda ancla de rescate
        assert t_update._git(repo, "rev-parse", "HEAD", env=entorno).stdout.strip() == prev
        assert not list(backup.glob("update_*.sql.gz"))


class TestBackup:
    def test_con_postgres_parado_falla_con_mensaje_y_estado_visible(self, tmp_path):
        ctx = t_backup._preparar(tmp_path)
        extra = _parar_bd(ctx["bin"], tmp_path, "siempre")
        r = t_backup._ejecutar(ctx, extra_env=extra)
        assert r.returncode != 0
        assert "No pude medir" in _salida(r)
        assert not list(ctx["backup"].glob("backup_*.sql.gz"))
        estado = (ctx["status"] / "status.json").read_text(encoding="utf-8")
        assert '"failed"' in estado and '"pg_dump_failed"' in estado     # /estado lo ve, con una causa que ya traduce


class TestRestaurarDatos:
    def test_si_no_se_puede_medir_la_bd_no_la_toca_y_lo_dice(self, tmp_path):
        ctx = t_restaurar._preparar(tmp_path)
        extra = _parar_bd(ctx["bin"], tmp_path, "solo_tamano")
        r = t_restaurar._ejecutar(ctx, extra_env=extra)
        assert r.returncode != 0
        assert "No pude medir" in _salida(r) and "No se ha tocado la BD" in _salida(r)
        t_restaurar._sin_destructivos(ctx)


def _bash(codigo: str, tmp_path: Path, extra_path: Path | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": f"{extra_path}:/usr/bin:/bin" if extra_path else "/usr/bin:/bin", "HOME": str(tmp_path)}
    return subprocess.run(["bash", "-c", f"set -euo pipefail; source {SCRIPTS}/_espacio.sh; {codigo}"],
                          capture_output=True, text=True, env=env, timeout=30)


class TestHelper:
    def test_tamano_bd_kb_no_mata_al_script_si_no_puede_medir(self, tmp_path):
        r = _bash('COMPOSE=(false); DB_USER=u; DB_NAME=d; T="$(tamano_bd_kb)"; echo "[${T}]"', tmp_path)
        assert r.returncode == 0 and r.stdout.strip() == "[]", r.stdout + r.stderr

    @pytest.mark.parametrize("necesario", ["", "abc", "12x"])
    def test_un_tamano_que_no_se_pudo_medir_no_se_toma_como_cero(self, tmp_path, necesario):
        r = _bash(f'exigir_espacio_kb 999999999 "{necesario}" "la prueba" && echo PASA || echo "rc=$?"', tmp_path)
        assert r.stdout.strip() == "rc=2" and "No pude medir" in r.stderr

    def test_un_tamano_numerico_sigue_comparandose_igual(self, tmp_path):
        ok = _bash('exigir_espacio_kb 999999999 1000 "la prueba" && echo PASA', tmp_path)
        assert ok.stdout.strip() == "PASA"
        corto = _bash('exigir_espacio_kb 10 1000 "la prueba" && echo PASA || echo "rc=$?"', tmp_path)
        assert corto.stdout.strip() == "rc=1" and "No hay espacio suficiente" in corto.stderr

    def test_el_tamano_descomprimido_es_exacto_aunque_gzip_l_se_equivoque(self, tmp_path):
        """`gzip -l` guarda el tamaño sin comprimir en 32 bits: con >4 GiB da el módulo. Aquí un `gzip` que miente en -l."""
        datos = b"x" * (3 * 1024 * 1024)
        dump = tmp_path / "d.sql.gz"
        dump.write_bytes(gzip.compress(datos))
        shim = tmp_path / "shim"
        shim.mkdir()
        real = shutil.which("gzip")
        (shim / "gzip").write_text(
            f'#!/usr/bin/env bash\nif [[ "$1" == "-l" ]]; then printf "compressed uncompressed ratio name\\n 10 %s 0.0%% x\\n" 1000; exit 0; fi\nexec {real} "$@"\n',
            encoding="utf-8")
        (shim / "gzip").chmod(0o755)
        r = _bash(f'tamano_descomprimido_kb "{dump}"', tmp_path, extra_path=shim)
        assert r.stdout.strip() == str(3 * 1024)

    def test_un_dump_ilegible_da_vacio_y_no_mata_al_script(self, tmp_path):
        malo = tmp_path / "malo.sql.gz"
        malo.write_bytes(b"no es gzip")
        r = _bash(f'T="$(tamano_descomprimido_kb "{malo}")"; echo "[${{T}}]"', tmp_path)
        assert r.returncode == 0 and r.stdout.strip() == "[]"


class TestDockerDePegaDeLosEscenarios:
    """Los escenarios aislados (`tests/escenarios/`, 88 casos que se saltan sin root o Docker con debian:12) usan un `docker` de
    pega que DEBE contestar a la medición de la BD. Si no lo hace, `backup.sh` aborta con «No pude medir» y el escenario
    dice «no funcionó como root» (P15), que despista. Esta prueba corre en cualquier máquina y falla diciendo la causa."""

    def _stub(self, tmp_path: Path) -> Path:
        texto = (RAIZ / "tests" / "escenarios" / "_comun.sh").read_text(encoding="utf-8")
        inicio = texto.index("<<'STUB'\n", texto.index("poner_docker_de_pega()")) + len("<<'STUB'\n")
        cuerpo = texto[inicio:texto.index("\nSTUB\n", inicio) + 1]
        docker = tmp_path / "docker"
        docker.write_text(cuerpo, encoding="utf-8")
        docker.chmod(0o755)
        (tmp_path / "env").write_text("DB_PASSWORD=x\n", encoding="utf-8")
        return docker

    def test_el_docker_de_pega_contesta_con_un_numero_a_la_medicion_de_la_bd(self, tmp_path):
        docker = self._stub(tmp_path)
        env = {"PATH": "/usr/bin:/bin", "STUB_LOG": str(tmp_path / "log")}
        r = subprocess.run(
            ["bash", "-c", f'set -euo pipefail; source {SCRIPTS}/_espacio.sh; '
                           f'COMPOSE=({docker} compose --env-file {tmp_path}/env); DB_USER=u; DB_NAME=d; '
                           'echo "[$(tamano_bd_kb)]"'],
            capture_output=True, text=True, env=env, timeout=30)
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.strip().strip("[]").isdigit(), (
            "el `docker` de pega de tests/escenarios/_comun.sh no contesta al tamaño de la BD (pg_database_size): "
            "backup.sh/update.sh/rollback.sh/restaurar_datos.sh abortarían con «No pude medir» en los escenarios")


def _kb(necesario: int) -> int:
    return necesario + necesario // 10 + 65536                           # necesario + 10 % + 64 MiB (en KiB)


class TestUmbralesDeEspacio:
    """#123 (QA, A3 de #385): el margen del 10 %, los 64 MiB y la frontera de `exigir_espacio_kb` se discriminan por separado."""

    @pytest.mark.parametrize("necesario", [0, 1000, 100000, 5_000_000])
    def test_justo_el_total_pasa_y_uno_menos_no(self, tmp_path, necesario):
        total = _kb(necesario)
        ok = _bash(f'exigir_espacio_kb {total} {necesario} "la prueba" && echo PASA || echo "rc=$?"', tmp_path)
        assert ok.stdout.strip() == "PASA", (necesario, ok.stdout, ok.stderr)
        corto = _bash(f'exigir_espacio_kb {total - 1} {necesario} "la prueba" && echo PASA || echo "rc=$?"', tmp_path)
        assert corto.stdout.strip() == "rc=1" and "No hay espacio suficiente" in corto.stderr

    def test_el_mensaje_da_las_cifras_en_mb(self, tmp_path):
        r = _bash('exigir_espacio_kb 2048 1024000 "la prueba" || true', tmp_path)
        assert "quedan 2 MB" in r.stderr and f"hacen falta {_kb(1024000) // 1024} MB" in r.stderr

    @pytest.mark.parametrize("libre", ["", "abc"])
    def test_un_espacio_libre_no_medible_no_es_disco_lleno(self, tmp_path, libre):
        r = _bash(f'exigir_espacio_kb "{libre}" 1000 "la prueba" && echo PASA || echo "rc=$?"', tmp_path)
        assert r.stdout.strip() == "rc=2" and "No pude medir el espacio libre" in r.stderr


DF_POR_RUTA = """#!/usr/bin/env bash
set -euo pipefail
kb="${FAKE_DF_KB:-99999999}"
if [[ "$*" == *"${OFFSITE_DIR:?}"* ]]; then kb="${FAKE_DF_OFFSITE_KB:-99999999}"; fi
printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
printf '/ 100000000 1 %s 1%% /\n' "$kb"
"""


class TestBackupOffsiteSinEspacio:
    def test_si_el_disco_de_respaldo_no_tiene_sitio_se_conserva_la_copia_local_y_se_avisa(self, tmp_path):
        ctx = t_backup._preparar(tmp_path)
        (ctx["bin"] / "df").write_text(DF_POR_RUTA, encoding="utf-8")
        r = t_backup._ejecutar(ctx, extra_env={"OFFSITE_DIR": str(ctx["offsite"]), "FAKE_DF_OFFSITE_KB": "1024"})
        assert r.returncode != 0 and "fuera del disco" in _salida(r)
        assert list(ctx["backup"].glob("backup_*.sql.gz"))                 # la copia local sigue
        assert not list(ctx["offsite"].glob("backup_*.sql.gz"))            # y no se intentó copiar fuera
        assert '"disk_full"' in (ctx["status"] / "status.json").read_text(encoding="utf-8")


class TestProbarRestauracionSinMedir:
    def test_con_postgres_parado_no_se_publica_como_disco_lleno(self, tmp_path):
        from tests import test_restore_script as t_restore

        ctx = t_restore._preparar(tmp_path)
        extra = _parar_bd(ctx["bin"], tmp_path, "siempre")
        r = t_restore._ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"], extra_env=extra)
        assert r.returncode != 0 and "No pude medir" in _salida(r)
        estado = t_restore._estado(ctx)
        assert estado["status"] == "failed" and estado["error"] == "restore_failed"     # no «disk_full»
        assert "disk_full" not in str(estado)

    def test_con_poco_espacio_si_se_publica_como_disco_lleno(self, tmp_path):
        from tests import test_restore_script as t_restore

        ctx = t_restore._preparar(tmp_path)
        r = t_restore._ejecutar(ctx, dump=ctx["dump"], manifest=ctx["manifest"], extra_env={"FAKE_PG_FREE_KB": "1"})
        assert r.returncode != 0 and t_restore._estado(ctx)["error"] == "disk_full"
