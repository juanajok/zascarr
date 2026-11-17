# ruff: noqa: E501
"""F-18 (SecOps) — T-10/T-21 con PostgreSQL REAL y el script de producción de punta a punta.

Reproduce, invertida, la prueba C-10 de SecOps: una copia hecha con la contraseña/vigencia A se restaura sobre una
instalación que ya está en B; la contraseña que vale es la de AHORA (`max(vigente, copia)+1` cierra las sesiones),
la `secret_key`, el `base_url` y los interruptores son los vigentes y las claves de integración son las de la copia.

No usa `TEST_DATABASE_URL` (no hay cliente `psql` en el host): levanta un proyecto Compose aislado con
`postgres:16-alpine` y ejecuta el script REAL, con renombrado real de bases. Se salta si no hay Docker; no toca
producción ni la Pi.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SCRIPT = RAIZ / "scripts" / "restaurar_datos.sh"
TS = "20260101_120000"

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="scripts de shell POSIX")


def _docker_ok() -> bool:
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _docker_ok(), reason="requiere Docker arrancado")


class _Salud(BaseHTTPRequestHandler):
    """El `Health` que espera el script; la «app» del compose solo existe para `stop`/`up`."""

    def do_GET(self):  # noqa: N802 — API de BaseHTTPRequestHandler
        cuerpo = b'{"status":"healthy","checks":{"database":"ok"}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, *_args):
        pass


class Proyecto:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp = tmp_path
        self.nombre = f"zascarr-it-{os.getpid()}-{tmp_path.name[-6:].lower()}".replace("_", "-")
        self.compose = tmp_path / "docker-compose.yml"
        self.env = tmp_path / ".env"
        self.backup = tmp_path / "backup"
        self.status = tmp_path / "status"
        self.repo = tmp_path / "repo"
        self.backup.mkdir()
        self.status.mkdir()
        self.env.write_text("DB_PASSWORD=test\n", encoding="utf-8")
        self.compose.write_text(
            f"""name: {self.nombre}
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: comics_admin
      POSTGRES_PASSWORD: test
      POSTGRES_DB: zascarr
  zascarr:
    image: postgres:16-alpine
    entrypoint: ["/bin/sh", "-c"]
    command: ["sleep infinity"]
""",
            encoding="utf-8",
        )
        (self.repo / "scripts").mkdir(parents=True)
        (self.repo / "README.md").write_text("repo\n", encoding="utf-8")
        self._git("init", "-q")
        self._git("add", ".")
        self._git("-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")
        self.head = self._git("rev-parse", "HEAD").stdout.strip()
        self._salud = HTTPServer(("127.0.0.1", 0), _Salud)
        self._hilo = threading.Thread(target=self._salud.serve_forever, daemon=True)

    # ── docker ──────────────────────────────────────────────────────────────────────────────────────────
    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True, text=True)

    def _compose(self, *args: str, **kw) -> subprocess.CompletedProcess:
        return subprocess.run(["docker", "compose", "-f", str(self.compose), "--env-file", str(self.env), *args],
                              capture_output=True, text=True, timeout=180, **kw)

    def psql(self, db: str, sql: str | None = None, *, entrada: str | None = None) -> subprocess.CompletedProcess:
        args = ["exec", "-T", "postgres", "psql", "-U", "comics_admin", "-v", "ON_ERROR_STOP=1", "-d", db]
        if sql is not None:
            args += ["-At", "-c", sql]
        return self._compose(*args, input=entrada)

    def esperar_postgres(self) -> None:
        limite = time.monotonic() + 90
        while time.monotonic() < limite:
            if self._compose("exec", "-T", "postgres", "pg_isready", "-U", "comics_admin",
                             "-d", "zascarr").returncode == 0:
                return
            time.sleep(0.5)
        raise AssertionError("PostgreSQL de pruebas no arrancó")

    def arrancar(self) -> None:
        r = self._compose("up", "-d", "postgres", "zascarr")
        assert r.returncode == 0, r.stderr
        self.esperar_postgres()
        self._hilo.start()

    def parar(self) -> None:
        self._salud.shutdown()
        self._compose("down", "-v", "--remove-orphans")

    @property
    def health_url(self) -> str:
        return f"http://127.0.0.1:{self._salud.server_address[1]}/api/health"

    # ── datos ───────────────────────────────────────────────────────────────────────────────────────────
    def crear_esquema(self, seguridad: dict, *, series: int = 2, issues: int = 1, files: int = 3) -> None:
        ddl = """
        CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY);
        CREATE TABLE runtime_settings (id integer PRIMARY KEY, "values" jsonb NOT NULL);
        CREATE TABLE series (id integer PRIMARY KEY);
        CREATE TABLE issues (id integer PRIMARY KEY, series_id integer);
        CREATE TABLE files (id integer PRIMARY KEY, issue_id integer);
        CREATE TABLE vinculacion_operaciones (id integer PRIMARY KEY, series_id integer);
        CREATE TABLE wishlist (id integer PRIMARY KEY, series_id integer, issue_id integer);
        CREATE TABLE colecciones (id integer PRIMARY KEY);
        INSERT INTO alembic_version VALUES ('0020');
        """
        r = self.psql("zascarr", entrada=ddl)
        assert r.returncode == 0, r.stderr
        self.cambiar_seguridad(seguridad)
        for tabla, n, columnas, relleno in (
            ("series", series, "", ""),
            ("issues", issues, ", series_id", ", 0"),
            ("files", files, ", issue_id", ", 0"),
            ("colecciones", 4, "", ""),
        ):
            if not n:
                continue
            valores = ",".join(f"({i}{relleno})" for i in range(n))
            r = self.psql("zascarr", f"INSERT INTO {tabla} (id{columnas}) VALUES {valores}")
            assert r.returncode == 0, r.stderr

    def cambiar_seguridad(self, valores: dict) -> None:
        """Escribe la fila con un literal entre comillas de dólar (los valores hostiles llevan comillas y saltos)."""
        datos = json.dumps(valores, ensure_ascii=False)
        etiqueta = "fila_prueba_c10"
        while f"${etiqueta}$" in datos:
            etiqueta += "x"
        sql = (f'INSERT INTO runtime_settings (id, "values") VALUES (1, ${etiqueta}${datos}${etiqueta}$::jsonb) '
               f'ON CONFLICT (id) DO UPDATE SET "values" = EXCLUDED."values";')
        r = self.psql("zascarr", entrada=sql)
        assert r.returncode == 0, r.stderr

    def leer_seguridad(self) -> dict:
        r = self.psql("zascarr", "select \"values\"::text from runtime_settings where id=1")
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout.strip())

    def crear_copia(self) -> None:
        volcado = self._compose("exec", "-T", "postgres", "pg_dump", "-U", "comics_admin", "zascarr")
        assert volcado.returncode == 0, volcado.stderr
        datos = volcado.stdout.encode("utf-8")
        dump = self.backup / f"backup_{TS}.sql.gz"
        dump.write_bytes(gzip.compress(datos))
        (self.backup / f"MANIFIESTO-backup_{TS}.json").write_text(json.dumps({
            "schema": 1, "backup": dump.name, "sha256": hashlib.sha256(dump.read_bytes()).hexdigest(),
            "bytes": dump.stat().st_size, "alembic": "0020",
            "codigo_destino_sha_completo": self.head, "codigo_desplegado_sha_completo": self.head,
        }), encoding="utf-8")

    def ejecutar(self, *, timeout: int = 180) -> subprocess.CompletedProcess:
        env = dict(os.environ)
        env.update({
            "REPO_DIR": str(self.repo), "ENV_FILE": str(self.env), "COMPOSE_FILE": str(self.compose),
            "BACKUP_DIR": str(self.backup), "BACKUP_STATUS_DIR": str(self.status),
            "DB_NAME": "zascarr", "DB_USER": "comics_admin", "HEALTH_URL": self.health_url,
            "HEALTH_TIMEOUT": "10", "HEALTH_INTERVAL": "1",
            "ZASCARR_PRUEBAS": "1", "OPS_LOCK_FILE": str(self.tmp / "ops.lock"),
            "PROYECTO_PRODUCCION": self.nombre,
        })
        return subprocess.run(["bash", str(SCRIPT), "--produccion", "--copia", TS], env=env,
                              capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


SEGURIDAD_COPIA = {
    "auth_mode": "password", "auth_username": "viejo",
    "auth_password_hash": "pbkdf2_sha256$10000$6161$" + "aa" * 32,   # contraseña A (copia)
    "secret_key": "sk-vieja", "base_url": "https://viejo", "auth_session_version": 3,
    "comicvine_enabled": True, "webhook_url": "https://webhook-viejo",
    "prowlarr_api_key": "clave-copia", "prowlarr_url": "http://prowlarr-copia:9696",
    "_marcador_interno": "de-la-copia", "fuentes_heredadas": True,
}
SEGURIDAD_VIGENTE = {
    "auth_mode": "password", "auth_username": "ana",
    "auth_password_hash": "pbkdf2_sha256$10000$6262$" + "bb" * 32,   # contraseña B (vigente)
    "secret_key": "sk-nueva", "base_url": "https://nuevo", "auth_session_version": 7,
    "comicvine_enabled": False, "webhook_enabled": True,
    "webhook_url": "https://webhook-nuevo", "webhook_token": "token-vigente",
    "prowlarr_api_key": "clave-vigente", "prowlarr_url": "http://prowlarr-vigente:9696",
    "fuentes_heredadas": False,
}


def test_c10_invertida_con_postgresql_real(tmp_path):
    """AC-23…AC-29/AC-33: A no vuelve, B vale, sesión max+1, integraciones de la copia y política vigente."""
    proyecto = Proyecto(tmp_path)
    proyecto.arrancar()
    try:
        proyecto.crear_esquema(SEGURIDAD_COPIA)
        proyecto.crear_copia()
        # La instalación sigue viva y cambia la seguridad después de la copia (ventana de C-10).
        proyecto.cambiar_seguridad(SEGURIDAD_VIGENTE)
        serie_nueva = proyecto.psql("zascarr", "INSERT INTO series (id) VALUES (99) RETURNING id")
        assert serie_nueva.returncode == 0, serie_nueva.stderr

        r = proyecto.ejecutar()
        assert r.returncode == 0, r.stdout + r.stderr

        final = proyecto.leer_seguridad()
        assert final["auth_password_hash"] == SEGURIDAD_VIGENTE["auth_password_hash"]   # B sigue valiendo
        assert final["auth_password_hash"] != SEGURIDAD_COPIA["auth_password_hash"]     # A no vuelve
        assert final["secret_key"] == "sk-nueva"
        assert final["auth_mode"] == "password" and final["auth_username"] == "ana"
        assert final["base_url"] == "https://nuevo"
        assert final["auth_session_version"] == 8                                      # max(7, 3) + 1
        assert final["comicvine_enabled"] is False                                     # política vigente
        assert final["webhook_url"] == "https://webhook-nuevo" and final["webhook_token"] == "token-vigente"
        assert final["prowlarr_api_key"] == "clave-copia"                              # integración de la copia
        assert final["prowlarr_url"] == "http://prowlarr-copia:9696"
        assert final["_marcador_interno"] == "de-la-copia"
        assert final["fuentes_heredadas"] is False

        # Los datos son los de la copia: la fila 99 escrita DESPUÉS del dump ya no está.
        series = proyecto.psql("zascarr", "select count(*) from series")
        assert series.stdout.strip() == "2", series.stderr
        # El cambio fue por renombrado: la previa se borró y no queda base de restauración.
        dbs = proyecto.psql("postgres", "select datname from pg_database order by datname").stdout
        assert "zascarr_restaurando" not in dbs and "zascarr_previa" not in dbs
        # La copia previa existe, es 0600 y es un pg_dump legible.
        previas = sorted(proyecto.backup.glob("rollback-safety_*.sql.gz"))
        assert len(previas) == 1 and (previas[0].stat().st_mode & 0o777) == 0o600
        assert b"PostgreSQL database dump" in gzip.decompress(previas[0].read_bytes())[:200]
        # Estado final de la interfaz: `hecha`, con recuentos y sin cadenas libres.
        estado = json.loads((proyecto.status / "ops-restaurar.json").read_text(encoding="utf-8"))
        assert estado["resultado"] == "hecha" and estado["base_en_su_sitio"] is True
        assert estado["recuentos"] == {"series": 2, "issues": 1, "files": 3}
    finally:
        proyecto.parar()


def test_la_seguridad_vigente_hostil_vuelve_byte_a_byte(tmp_path):
    """AC-45/T-21: comillas, `$$`, barra, salto de línea y Unicode en la fila vigente se reaplican idénticos."""
    proyecto = Proyecto(tmp_path)
    proyecto.arrancar()
    try:
        proyecto.crear_esquema(SEGURIDAD_COPIA)
        proyecto.crear_copia()
        hostil = dict(SEGURIDAD_VIGENTE)
        hostil["auth_username"] = "a'b\"c$$d\\e\nf-ñ-😀"
        hostil["base_url"] = "https://xn--ejemplo.example/ñ?x='1'&y=$$z"
        hostil["webhook_token"] = "to'ken$$\\n-salto"
        proyecto.cambiar_seguridad(hostil)
        r = proyecto.ejecutar()
        assert r.returncode == 0, r.stdout + r.stderr
        final = proyecto.leer_seguridad()
        assert final["auth_username"] == hostil["auth_username"]
        assert final["base_url"] == hostil["base_url"]
        assert final["webhook_token"] == hostil["webhook_token"]
    finally:
        proyecto.parar()
