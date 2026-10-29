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
            'if [[ "$*" == *information_schema.tables* ]]; then echo 5; exit 0; fi\n'
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
