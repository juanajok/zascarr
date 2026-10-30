"""Pruebas del fixture reproducible de 123a-i.

No usa base de datos: comprueba recuentos, tipos, tamaño, determinismo y la
salvaguarda `ZASCARR_ENTORNO=123a`. El token se verifica con el mismo secreto
sintético que el generador deja en el directorio de salida.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "aceptacion" / "preparar_fixture_123a.py"


def _entorno(**extra: str) -> dict:
    env = os.environ.copy()
    env.update(
        {
            "ZASCARR_ENTORNO": "123a",
            "PYTHONPATH": str(RAIZ / "src"),
        }
    )
    env.update(extra)
    return env


def _ejecutar(salida: Path, *, env: dict | None = None, extra: list[str] | None = None):
    args = [sys.executable, str(SCRIPT), "--salida", str(salida)]
    if extra:
        args += extra
    return subprocess.run(
        args,
        env=env or _entorno(),
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )


@pytest.mark.skipif(sys.platform == "win32", reason="rutas y permisos POSIX")
class TestFixture123a:
    def test_recuentos_y_tipos(self, tmp_path):
        salida = tmp_path / "fixture"
        r = _ejecutar(salida)
        assert r.returncode == 0, r.stdout + r.stderr

        resumen = json.loads((salida / "resumen.json").read_text(encoding="utf-8"))
        assert resumen["series"] == 4
        assert resumen["issues"] == 6
        assert resumen["files"] == 40
        assert resumen["files_por_formato"] == {"cbz": 30, "cbr": 9, "cb7": 1}
        assert resumen["con_issue"] == 24
        assert resumen["sin_issue"] == 16
        assert resumen["is_missing"] == 2
        assert resumen["sin_sha256"] == 1
        assert resumen["con_formato_contenido"] == 1
        assert resumen["vinculacion_operaciones"] == 3
        assert resumen["wishlist"] == {"total": 3, "wanted": 2, "imported": 1}
        assert resumen["ficheros_en_disco"] == 38

    def test_biblioteca_maximo_5_mb_y_ficheros_unicos(self, tmp_path):
        salida = tmp_path / "fixture"
        assert _ejecutar(salida).returncode == 0

        biblioteca = salida / "biblioteca"
        ficheros = [p for p in biblioteca.rglob("*") if p.is_file()]
        assert len(ficheros) == 38
        assert sum(p.stat().st_size for p in ficheros) <= 5 * 1024 * 1024
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in ficheros]
        assert len(set(hashes)) == len(hashes)

    def test_sql_no_usa_rutas_reales(self, tmp_path):
        salida = tmp_path / "fixture"
        assert _ejecutar(salida).returncode == 0
        sql = (salida / "seed.sql").read_text(encoding="utf-8")
        assert "/media/library/" in sql
        for prohibida in ("/var/lib/zascarr", "/media/data", "/home/", "/mnt/"):
            assert prohibida not in sql

    def test_token_sembrado_verifica(self, tmp_path):
        salida = tmp_path / "fixture"
        assert _ejecutar(salida).returncode == 0
        from zascarr.services.tokens_revision import verificar_token_vinculacion

        token = (salida / "token.txt").read_text(encoding="utf-8").strip()
        secreto = (salida / "secret_key.txt").read_text(encoding="utf-8").strip()
        firmado = verificar_token_vinculacion(token, secreto)
        assert firmado is not None
        assert firmado.operacion == "00000000-0000-0000-0000-000000000101"
        assert firmado.series_id == "00000000-0000-0000-0000-000000000001"

    def test_exige_entorno_123a(self, tmp_path):
        env = _entorno()
        env.pop("ZASCARR_ENTORNO", None)
        r = _ejecutar(tmp_path / "fixture", env=env)
        assert r.returncode != 0
        assert "ZASCARR_ENTORNO" in r.stderr

    def test_rechaza_otro_entorno(self, tmp_path):
        r = _ejecutar(tmp_path / "fixture", env=_entorno(ZASCARR_ENTORNO="produccion"))
        assert r.returncode != 0
        assert "123a" in r.stderr

    def test_segunda_ejecucion_sin_reset_falla_y_con_reset_pasa(self, tmp_path):
        salida = tmp_path / "fixture"
        assert _ejecutar(salida).returncode == 0
        r = _ejecutar(salida)
        assert r.returncode != 0
        assert "reset" in r.stderr.lower() or "existe" in r.stderr.lower()
        r = _ejecutar(salida, extra=["--reset"])
        assert r.returncode == 0, r.stdout + r.stderr

    def test_aplicar_sin_database_url_falla(self, tmp_path):
        salida = tmp_path / "fixture"
        r = _ejecutar(salida, extra=["--aplicar"])
        assert r.returncode != 0
        assert "database" in r.stderr.lower() or "DATABASE_URL" in r.stderr

    def _psql_falso(self, tmp_path: Path) -> tuple[Path, Path]:
        bin_ = tmp_path / "bin"
        bin_.mkdir()
        log = tmp_path / "psql.log"
        log.write_text("", encoding="utf-8")
        psql = bin_ / "psql"
        psql.write_text(
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            'echo "$*" >> "$PSQL_LOG"\n'
            'echo "PGPASSWORD=${PGPASSWORD:-}" >> "$PSQL_LOG.env"\n'
            'if [[ "$*" == *information_schema.tables* ]]; then echo 5; exit 0; fi\n'
            'if [[ "$*" == *shobj_description* ]]; then echo "${FAKE_PSQL_MARCA-zascarr-123a-aislada}"; exit 0; fi\n'
            'if [[ "$*" == *"||"* ]]; then echo "4|6|40|3|3"; exit 0; fi\n'
            'if [[ "$*" == *"from series)+(select count(*) from issues"* ]]; then\n'
            '  echo "$FAKE_PSQL_CUENTA"; exit 0;\n'
            "fi\n"
            "exit 0\n",
            encoding="utf-8",
        )
        psql.chmod(0o755)
        return bin_, log

    def test_aplicar_rechaza_bd_no_vacia(self, tmp_path):
        salida = tmp_path / "fixture"
        bin_, log = self._psql_falso(tmp_path)
        env = _entorno(
            PATH=f"{bin_}:{os.environ['PATH']}",
            FAKE_PSQL_CUENTA="1",
            PSQL_LOG=str(log),
        )
        r = _ejecutar(
            salida,
            env=env,
            extra=[
                "--aplicar",
                "--database-url",
                "postgresql://test@127.0.0.1:15432/test",
            ],
        )
        assert r.returncode != 0
        assert "vacía" in r.stderr.lower() or "reset" in r.stderr.lower()

    def test_aplicar_permite_la_url_aislada(self, tmp_path):
        salida = tmp_path / "fixture"
        bin_, log = self._psql_falso(tmp_path)
        env = _entorno(
            PATH=f"{bin_}:{os.environ['PATH']}",
            FAKE_PSQL_CUENTA="0",
            PSQL_LOG=str(log),
        )
        r = _ejecutar(
            salida,
            env=env,
            extra=[
                "--aplicar",
                "--database-url",
                "postgresql://test@127.0.0.1:15432/test",
            ],
        )
        assert r.returncode == 0, r.stdout + r.stderr
        llamadas = log.read_text(encoding="utf-8")
        assert "information_schema.tables" in llamadas
        assert "-f" in llamadas
        assert (salida / "seed.sql").exists()

    @pytest.mark.parametrize(
        "url",
        [
            "postgresql://u:p@127.0.0.1:5432/zascarr",
            "postgresql://u:p@db.example:15432/zascarr",
            "postgresql://u:p@127.0.0.1/zascarr",
            # el destino efectivo lo cambian los parámetros de libpq, no el host/puerto de la autoridad
            "postgresql://u:p@127.0.0.1:15432/zascarr?host=db.example&port=5432",
            "postgresql://u:p@127.0.0.1:15432/zascarr?hostaddr=10.0.0.5",
            "postgresql://u:p@127.0.0.1:15432/zascarr?service=produccion",
            "postgresql://u:p@127.0.0.1:15432,db.example:5432/zascarr",
        ],
    )
    def test_aplicar_rechaza_url_fuera_del_aislado_antes_de_psql(self, tmp_path, url):
        salida = tmp_path / "fixture"
        bin_ = tmp_path / "bin"
        bin_.mkdir()
        marca = tmp_path / "psql-llamado"
        psql = bin_ / "psql"
        psql.write_text(
            f'#!/usr/bin/env bash\nset -euo pipefail\n: > "{marca}"\nexit 0\n',
            encoding="utf-8",
        )
        psql.chmod(0o755)
        env = _entorno(PATH=f"{bin_}:{os.environ['PATH']}")
        r = _ejecutar(salida, env=env, extra=["--aplicar", "--database-url", url])
        assert r.returncode != 0
        assert "15432" in r.stderr or "aislada" in r.stderr.lower()
        assert not marca.exists()
        assert not salida.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="rutas y permisos POSIX")
class TestSalvaguardas123a:
    """#123 (SecOps X-1..X-3): el reset solo borra lo reconocible, la BD exige su marca y la contraseña no va en argv."""

    def _generar(self, tmp_path: Path) -> Path:
        salida = tmp_path / "fixture"
        r = _ejecutar(salida)
        assert r.returncode == 0, r.stderr
        return salida

    def test_reset_no_borra_un_directorio_con_ficheros_ajenos(self, tmp_path):
        salida = self._generar(tmp_path)
        (salida / "mis-notas.txt").write_text("importante", encoding="utf-8")
        r = _ejecutar(salida, extra=["--reset"])
        assert r.returncode != 0 and "no lo borro" in r.stderr
        assert (salida / "mis-notas.txt").read_text(encoding="utf-8") == "importante"
        assert (salida / "seed.sql").exists()                           # y no tocó nada del fixture

    def test_reset_no_sigue_enlaces_simbolicos(self, tmp_path):
        salida = self._generar(tmp_path)
        fuera = tmp_path / "fuera"
        fuera.mkdir()
        (fuera / "dato.txt").write_text("no se toca", encoding="utf-8")
        (salida / "token.txt").unlink()
        (salida / "token.txt").symlink_to(fuera / "dato.txt")
        r = _ejecutar(salida, extra=["--reset"])
        assert r.returncode != 0
        assert (fuera / "dato.txt").read_text(encoding="utf-8") == "no se toca"

    def test_reset_de_un_fixture_reconocible_lo_regenera(self, tmp_path):
        salida = self._generar(tmp_path)
        r = _ejecutar(salida, extra=["--reset"])
        assert r.returncode == 0, r.stderr
        assert (salida / "seed.sql").exists() and (salida / ".fixture-123a").read_text() == "1\n"

    def _con_psql_falso(self, tmp_path: Path, **extra):
        bin_ = tmp_path / "bin"
        bin_.mkdir()
        log = tmp_path / "psql.log"
        log.write_text("", encoding="utf-8")
        (tmp_path / "psql.log.env").write_text("", encoding="utf-8")
        psql = bin_ / "psql"
        psql.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            'echo "$*" >> "$PSQL_LOG"\n'
            'echo "PGPASSWORD=${PGPASSWORD:-}" >> "$PSQL_LOG.env"\n'
            'if [[ "$*" == *information_schema.tables* ]]; then echo 5; exit 0; fi\n'
            'if [[ "$*" == *shobj_description* ]]; then echo "${FAKE_PSQL_MARCA-zascarr-123a-aislada}"; exit 0; fi\n'
            'if [[ "$*" == *"||"* ]]; then echo "4|6|40|3|3"; exit 0; fi\n'
            'if [[ "$*" == *"from series)+(select count(*) from issues"* ]]; then echo 0; exit 0; fi\n'
            "exit 0\n", encoding="utf-8")
        psql.chmod(0o755)
        return _entorno(PATH=f"{bin_}:{os.environ['PATH']}", PSQL_LOG=str(log), **extra), log

    @pytest.mark.parametrize("marca", ["", "otra-cosa"])
    def test_sin_la_marca_de_la_bd_no_se_trunca_ni_se_aplica_nada(self, tmp_path, marca):
        env, log = self._con_psql_falso(tmp_path, FAKE_PSQL_MARCA=marca)
        r = _ejecutar(tmp_path / "fixture", env=env, extra=[
            "--aplicar", "--reset", "--database-url", "postgresql://test@127.0.0.1:15432/test"])
        assert r.returncode != 0 and "marca" in r.stderr.lower()
        llamadas = log.read_text(encoding="utf-8")
        assert "TRUNCATE" not in llamadas and " -f " not in f" {llamadas} "

    def test_la_contrasena_va_en_el_entorno_y_no_en_los_argumentos(self, tmp_path):
        env, log = self._con_psql_falso(tmp_path)
        r = _ejecutar(tmp_path / "fixture", env=env, extra=[
            "--aplicar", "--database-url", "postgresql://test:C0ntr4s3na-SINTETICA@127.0.0.1:15432/test"])
        assert r.returncode == 0, r.stderr
        assert "C0ntr4s3na-SINTETICA" not in log.read_text(encoding="utf-8")            # no en argv
        assert "PGPASSWORD=C0ntr4s3na-SINTETICA" in (tmp_path / "psql.log.env").read_text(encoding="utf-8")
        assert "127.0.0.1:15432/test" in log.read_text(encoding="utf-8")                # el destino se conserva
