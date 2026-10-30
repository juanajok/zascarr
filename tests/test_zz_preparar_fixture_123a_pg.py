"""Aplicación real del fixture de 123a en PostgreSQL (migrado a head).

Se ejecuta después de `test_restore_pg.py` a propósito: ambos crean/destruyen
bases desechables y el orden alfabético anterior hacía que este test dejara
actividad de DDL antes del test de restauración, que podía morir por deadlock.

El test crea una base desechable a partir de `TEST_DATABASE_URL`, aplica las
migraciones y ejecuta el `seed.sql` generado con `ON_ERROR_STOP=1`. No usa el
`--aplicar` del generador: la guardia de puerto 15432 se prueba aparte con un
`psql` doble. Así el job de PostgreSQL real no necesita el puerto aislado.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import unquote, urlparse, urlunparse

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "aceptacion" / "preparar_fixture_123a.py"
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
ALEMBIC = str(Path(sys.executable).with_name("alembic"))
if not Path(ALEMBIC).exists():
    ALEMBIC = shutil.which("alembic") or "alembic"

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL or not all(shutil.which(c) for c in ("psql", "createdb", "dropdb")),
    reason="requiere TEST_DATABASE_URL y los clientes de PostgreSQL",
)


def _pg_env(url: str) -> dict:
    limpa = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    u = urlparse(limpa)
    return {
        "PGHOST": u.hostname or "127.0.0.1",
        "PGPORT": str(u.port or 5432),
        "PGUSER": unquote(u.username or ""),
        "PGPASSWORD": unquote(u.password or ""),
        "PGDATABASE": u.path.lstrip("/"),
    }


def _url_con_db(url: str, nombre: str) -> str:
    u = urlparse(url)
    salida = urlunparse(u._replace(path=f"/{nombre}"))
    if salida.startswith("postgresql://"):
        return salida.replace("postgresql://", "postgresql+asyncpg://", 1)
    return salida


def _psql(pg: dict, sql: str) -> str:
    r = subprocess.run(
        ["psql", "-At", "-v", "ON_ERROR_STOP=1", "-c", sql],
        env={**os.environ, **pg},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip()


def test_seed_sql_se_aplica_en_postgres_real(tmp_path):
    base = TEST_DATABASE_URL
    assert base
    nombre = f"zascarr_fixture_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    pg = _pg_env(base)
    pg["PGDATABASE"] = nombre
    url_db = _url_con_db(base, nombre)

    creada = False
    try:
        subprocess.run(
            ["createdb", nombre],
            env={**os.environ, **_pg_env(base)},
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        creada = True

        env_migrar = {
            **os.environ,
            "DATABASE_URL": url_db,
            "PYTHONPATH": str(RAIZ / "src"),
        }
        migrado = subprocess.run(
            [ALEMBIC, "upgrade", "head"],
            cwd=RAIZ,
            env=env_migrar,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert migrado.returncode == 0, migrado.stdout + migrado.stderr

        cabezas = subprocess.run(
            [ALEMBIC, "heads"],
            cwd=RAIZ,
            env=env_migrar,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert cabezas.returncode == 0, cabezas.stdout + cabezas.stderr
        m_head = re.search(r"([0-9A-Za-z_]+) \(head\)", cabezas.stdout)
        assert m_head is not None, cabezas.stdout
        head = m_head.group(1)
        assert _psql(pg, "select version_num from alembic_version") == head

        salida = tmp_path / "fixture"
        env_fixture = {
            **os.environ,
            "ZASCARR_ENTORNO": "123a",
            "PYTHONPATH": str(RAIZ / "src"),
        }
        generado = subprocess.run(
            [sys.executable, str(SCRIPT), "--salida", str(salida)],
            env=env_fixture,
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert generado.returncode == 0, generado.stdout + generado.stderr

        seed = salida / "seed.sql"
        assert seed.exists()
        aplicado = subprocess.run(
            ["psql", "-v", "ON_ERROR_STOP=1", "-f", str(seed)],
            env={**os.environ, **pg},
            capture_output=True,
            text=True,
            timeout=180,
        )
        assert aplicado.returncode == 0, aplicado.stdout + aplicado.stderr

        assert (
            _psql(
                pg,
                "select (select count(*) from series)||'|'||(select count(*) from issues)"
                "||'|'||(select count(*) from files)||'|'||(select count(*) from "
                "vinculacion_operaciones)||'|'||(select count(*) from wishlist);",
            )
            == "4|6|40|3|3"
        )
        assert (
            _psql(
                pg,
                "select (select count(*) from files where issue_id is not null)||'|'||"
                "(select count(*) from files where is_missing)||'|'||"
                "(select count(*) from files where sha256_hash is null)||'|'||"
                "(select count(*) from files where metadata ? 'formato_contenido');",
            )
            == "24|2|1|1"
        )
        assert (
            _psql(
                pg,
                "select count(*) from issues i left join series s on s.id=i.series_id "
                "where s.id is null;",
            )
            == "0"
        )

        series_ids = set(
            re.findall(
                r"INSERT INTO series .*?VALUES \('([0-9a-f-]{36})'",
                seed.read_text(encoding="utf-8"),
            )
        )
        issues_sql = [
            linea
            for linea in seed.read_text(encoding="utf-8").splitlines()
            if linea.startswith("INSERT INTO issues ")
        ]
        assert len(issues_sql) == 6
        for linea in issues_sql:
            m = re.search(r"VALUES \('([0-9a-f-]{36})', '([0-9a-f-]{36})'", linea)
            assert m is not None, linea
            assert m.group(2) in series_ids, linea

        from zascarr.services.tokens_revision import verificar_token_vinculacion

        token = (salida / "token.txt").read_text(encoding="utf-8").strip()
        secreto = (salida / "secret_key.txt").read_text(encoding="utf-8").strip()
        firmado = verificar_token_vinculacion(token, secreto)
        assert firmado is not None
        assert firmado.series_id in series_ids

        valores = json.loads(_psql(pg, "select values::text from runtime_settings where id=1"))
        assert valores["secret_key"] == secreto
        for clave in (
            "comicvine_enabled",
            "anilist_enabled",
            "tebeosfera_enabled",
            "gcd_enabled",
            "prowlarr_enabled",
            "transmission_enabled",
            "amule_enabled",
        ):
            assert valores[clave] is False, clave
        assert valores["prowlarr_url"] == ""
        assert valores["transmission_url"] == ""
        assert valores["amule_url"] == ""
    finally:
        if creada:
            subprocess.run(
                ["dropdb", "--if-exists", "--force", nombre],
                env={**os.environ, **_pg_env(base)},
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
