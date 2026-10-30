"""
tests/test_health.py

Suite de /api/health. Objetivo principal: regresión del hallazgo E2E
release 1.0 — TransmissionClient/AMuleClient se llamaban secuencialmente
con timeout=30.0 cada uno; si ninguno respondía con RST inmediato (VPN aún
no arriba, servicio parado, firewall con DROP en vez de REJECT — nada raro
en una Pi real), /api/health tardaba hasta ~60s, y el HEALTHCHECK del
Dockerfile (--timeout=10s) marcaba el contenedor unhealthy de forma casi
permanente. Ahora corren en paralelo con un timeout corto propio.
"""

from __future__ import annotations

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app


class FakeSession:
    async def execute(self, _statement):
        return None


def _fake_db_client():
    async def _get_db():
        yield FakeSession()

    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _get_db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)

    return _Ctx()


async def _cuelga(segundos: float) -> bool:
    await asyncio.sleep(segundos)
    return True


@pytest.fixture
def clientes(monkeypatch):
    """Enciende o apaga Transmission y aMule (vienen apagados por defecto)."""

    def fijar(transmission: bool = True, amule: bool = True):
        s = get_settings()
        monkeypatch.setattr(s, "transmission_enabled", transmission)
        monkeypatch.setattr(s, "amule_enabled", amule)

    return fijar


@pytest.fixture(autouse=True)
def _backup_reciente(tmp_path_factory, monkeypatch):
    """#334: sin el fichero de estado, la copia ausente deja el health en
    `degraded`. Las pruebas que no son de backups parten de una copia reciente;
    las de TestHealthBackup sustituyen el fichero por el caso que prueban."""
    ruta = tmp_path_factory.mktemp("backup-status") / "status.json"
    ruta.write_text(
        json.dumps({"status": "ok", "error": None, "last_success_at_epoch": time.time()}),
        encoding="utf-8",
    )
    monkeypatch.setattr(get_settings(), "backup_status_file", str(ruta))


class TestHealthLatenciaAcotada:
    """Con los dos clientes ENCENDIDOS: apagados ni se sondean (ver TestClientesApagados)."""

    @pytest.fixture(autouse=True)
    def _encendidos(self, clientes):
        clientes()

    def test_transmission_y_amule_se_consultan_en_paralelo_no_en_serie(self):
        """Con el bug original (llamadas secuenciales), dos comprobaciones
        de 0.2s habrían tardado >= 0.4s. En paralelo deben tardar ~0.2s."""
        with (
            patch("zascarr.api.health._check_transmission", lambda: _cuelga(0.2)),
            patch("zascarr.api.health._check_amule", lambda: _cuelga(0.2)),
        ):
            with _fake_db_client() as client:
                t0 = time.monotonic()
                r = client.get("/api/health")
                elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed < 0.35, f"tardó {elapsed:.2f}s — ¿volvió a ser secuencial?"

    def test_servicio_que_no_responde_no_bloquea_mas_del_timeout_corto(self):
        """Un servicio que nunca responde (el caso real: firewall con DROP)
        no debe colgar /api/health más allá de su timeout interno corto,
        muy por debajo de los 30s del cliente HTTP subyacente."""
        with (
            patch("zascarr.api.health._check_transmission", lambda: _cuelga(999)),
            patch("zascarr.api.health._check_amule", lambda: _cuelga(999)),
        ):
            with _fake_db_client() as client:
                t0 = time.monotonic()
                r = client.get("/api/health")
                elapsed = time.monotonic() - t0

        assert r.status_code == 200
        assert elapsed < 5.0
        body = r.json()
        assert body["checks"]["transmission"] == "unreachable"
        assert body["checks"]["amule"] == "unreachable"

    def test_status_degraded_cuando_solo_falla_lo_opcional(self):
        with (
            patch("zascarr.api.health._check_transmission", AsyncMock(return_value=True)),
            patch("zascarr.api.health._check_amule", AsyncMock(return_value=False)),
            patch(
                "zascarr.api.health._database_status",
                AsyncMock(return_value=("ok", "Conectada y migrada.")),
            ),
        ):
            with _fake_db_client() as client:
                r = client.get("/api/health")

        assert r.status_code == 200
        body = r.json()
        assert body["checks"]["database"] == "ok"
        assert body["checks"]["transmission"] == "ok"
        assert body["checks"]["amule"] == "unreachable"
        assert body["status"] == "degraded"


class TestAlembicHead:
    def test_head_se_resuelve_desde_versions(self):
        from zascarr.api.health import _alembic_head

        head = _alembic_head()
        assert head, "no se pudo resolver el head de alembic desde alembic/versions"


class TestNo500PorEsquemaIncompleto:
    def test_ui_devuelve_503_no_500_crudo_con_tabla_ausente(self):
        """E6: una vista /ui/* con una tabla ausente degrada a un diagnóstico
        (503 con enlace a /estado), no a un 500 crudo con traceback."""
        from sqlalchemy.exc import ProgrammingError

        class _Orig(Exception):
            sqlstate = "42P01"  # undefined_table

        class _SesionRota:
            async def execute(self, _statement):
                raise ProgrammingError("SELECT 1", {}, _Orig())

        async def _get_db_rota():
            yield _SesionRota()

        app.dependency_overrides[get_db] = _get_db_rota
        try:
            client = TestClient(app, raise_server_exceptions=False)
            r = client.get("/ui/")
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert r.status_code == 503
        assert "Base de datos no lista" in r.text
        assert "/estado" in r.text


class TestArranqueDegradado:
    def test_bd_inaccesible_arranca_y_sirve_solo_diagnostico(self, monkeypatch):
        """E6: si Postgres no conecta al arrancar, la app levanta igual pero
        solo sirve diagnóstico — /api/health reporta `unreachable` y /ui/* falla
        cerrado con 503, en vez de no arrancar y no servir nada."""
        import zascarr.database as dbmod
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        bad_engine = create_async_engine("postgresql+asyncpg://nadie:nada@127.0.0.1:1/nada")
        bad_sesion = async_sessionmaker(bad_engine, expire_on_commit=False)
        monkeypatch.setattr(dbmod, "engine", bad_engine)
        monkeypatch.setattr(dbmod, "async_session_factory", bad_sesion)

        with TestClient(app, raise_server_exceptions=False) as client:
            r_health = client.get("/api/health")
            r_ui = client.get("/ui/")

        assert r_health.status_code == 200
        assert r_health.json()["checks"]["database"] == "unreachable"
        assert r_ui.status_code == 503


class TestClientesApagados:
    """Revisión visual (2026-10-20): Transmission y aMule apagados en Ajustes salían como «No
    disponible» con un punto rojo y ponían el semáforo en «Atención»; en una instalación nueva,
    siempre."""

    def test_apagado_es_disabled_y_ni_se_sondea(self, clientes):
        clientes(transmission=False, amule=False)
        sondas = AsyncMock(return_value=False)
        with (
            patch("zascarr.api.health._check_transmission", sondas),
            patch("zascarr.api.health._check_amule", sondas),
            patch(
                "zascarr.api.health._database_status",
                AsyncMock(return_value=("ok", "Conectada y migrada.")),
            ),
            _fake_db_client() as client,
        ):
            body = client.get("/api/health").json()
        assert body["checks"]["transmission"] == "disabled"
        assert body["checks"]["amule"] == "disabled"
        assert body["status"] == "healthy"
        sondas.assert_not_called()

    def test_solo_cuenta_el_que_esta_encendido(self, clientes):
        clientes(transmission=True, amule=False)
        with (
            patch("zascarr.api.health._check_transmission", AsyncMock(return_value=False)),
            patch(
                "zascarr.api.health._database_status",
                AsyncMock(return_value=("ok", "Conectada y migrada.")),
            ),
            _fake_db_client() as client,
        ):
            body = client.get("/api/health").json()
        assert body["checks"] == {
            **body["checks"],
            "transmission": "unreachable",
            "amule": "disabled",
        }
        assert body["status"] == "degraded"

    def test_estado_lo_pinta_desactivado_en_gris_y_fuera_del_resumen(self):
        from zascarr.web.routes import TEMPLATES_DIR

        html = (TEMPLATES_DIR / "estado.html").read_text(encoding="utf-8")
        assert 'disabled: "Desactivado"' in html
        assert 'disabled: "neutral"' in html
        assert 'if (level === "warn" || level === "bad") detailParts.push' in html


class TestHealthDisk:
    """#123b: checks.disk no bloquea, no mira la biblioteca de red y no hace unhealthy."""

    @pytest.fixture(autouse=True)
    def _base(self, clientes, monkeypatch, tmp_path):
        clientes(transmission=False, amule=False)
        monkeypatch.setattr(get_settings(), "disk_paths", str(tmp_path))
        monkeypatch.setattr(get_settings(), "disk_warn_free_mb", 2048)
        monkeypatch.setattr(get_settings(), "disk_error_free_mb", 512)

    def _body(self, monkeypatch, *, libre_mb: int):
        monkeypatch.setattr(
            "zascarr.api.health.shutil.disk_usage",
            lambda _ruta: type(
                "U", (), {"free": libre_mb * 1024 * 1024, "total": 10**12, "used": 0}
            )(),
        )
        with (
            patch(
                "zascarr.api.health._database_status",
                AsyncMock(return_value=("ok", "Conectada y migrada.")),
            ),
            patch(
                "zascarr.api.health._restore_status", return_value=("ok", "Restauración reciente")
            ),
            _fake_db_client() as client,
        ):
            return client.get("/api/health").json()

    def test_poco_espacio_es_warning_y_degraded(self, monkeypatch):
        body = self._body(monkeypatch, libre_mb=1024)
        assert body["checks"]["disk"] == "warning"
        assert body["status"] == "degraded"
        assert "disk" in body["warnings"]

    def test_sin_espacio_es_error_pero_no_unhealthy(self, monkeypatch):
        body = self._body(monkeypatch, libre_mb=100)
        assert body["checks"]["disk"] == "error"
        assert body["status"] == "degraded"

    def test_suficiente_es_ok_y_healthy(self, monkeypatch):
        body = self._body(monkeypatch, libre_mb=4096)
        assert body["checks"]["disk"] == "ok"
        assert body["status"] == "healthy"

    def test_estado_pinta_la_fila_de_disco(self):
        from zascarr.web.routes import TEMPLATES_DIR

        html = (TEMPLATES_DIR / "estado.html").read_text(encoding="utf-8")
        assert 'disk: "Disco"' in html
        assert "Espacio suficiente" in html
        assert "Libera espacio" in html


class TestHealthBackup:
    """#334: el aviso de copias se lee del fichero del host y no tumba /api/health."""

    @pytest.fixture(autouse=True)
    def _encendidos(self, clientes):
        clientes()

    def _estado(self, tmp_path, monkeypatch, **datos):
        ruta = tmp_path / "status.json"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        monkeypatch.setattr(get_settings(), "backup_status_file", str(ruta))
        return ruta

    def _pedir(self, db=("ok", "Conectada y migrada.")):
        with (
            patch("zascarr.api.health._check_transmission", AsyncMock(return_value=True)),
            patch("zascarr.api.health._check_amule", AsyncMock(return_value=True)),
            patch("zascarr.api.health._database_status", AsyncMock(return_value=db)),
            _fake_db_client() as client,
        ):
            return client.get("/api/health").json()

    def test_ok_fresco(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path, monkeypatch, status="ok", error=None, last_success_at_epoch=time.time()
        )
        body = self._pedir()
        assert body["checks"]["backup"] == "ok"
        assert body["status"] == "healthy"

    def test_failed_es_error_y_deja_el_global_en_degraded(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path,
            monkeypatch,
            status="failed",
            error="pg_dump_failed",
            last_success_at_epoch=time.time(),
        )
        body = self._pedir()
        assert body["checks"]["backup"] == "error"
        assert body["status"] == "degraded"
        assert "el volcado falló" in body["warnings"]["backup"]

    def test_degraded_anclas_es_warning(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path,
            monkeypatch,
            status="degraded",
            error="anchor_sync_failed",
            last_success_at_epoch=time.time(),
        )
        body = self._pedir()
        assert body["checks"]["backup"] == "warning"
        assert body["status"] == "degraded"
        assert "anclas" in body["warnings"]["backup"]

    @pytest.mark.parametrize("horas, esperado", [(30, "warning"), (50, "error")])
    def test_antiguedad_de_la_ultima_copia(self, tmp_path, monkeypatch, horas, esperado):
        self._estado(
            tmp_path,
            monkeypatch,
            status="ok",
            error=None,
            last_success_at_epoch=time.time() - horas * 3600,
        )
        body = self._pedir()
        assert body["checks"]["backup"] == esperado
        assert body["status"] == "degraded"

    def test_fichero_ausente_es_error_sin_500(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_settings(), "backup_status_file", str(tmp_path / "no-existe.json"))
        body = self._pedir()
        assert body["checks"]["backup"] == "error"
        assert body["status"] == "degraded"
        assert "No hay registro" in body["warnings"]["backup"]

    def test_json_invalido_es_error_sin_500(self, tmp_path, monkeypatch):
        ruta = tmp_path / "status.json"
        ruta.write_text("no es json", encoding="utf-8")
        monkeypatch.setattr(get_settings(), "backup_status_file", str(ruta))
        body = self._pedir()
        assert body["checks"]["backup"] == "error"
        assert body["status"] == "degraded"

    def test_bd_caida_sigue_siendo_unhealthy(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path,
            monkeypatch,
            status="failed",
            error="pg_dump_failed",
            last_success_at_epoch=time.time(),
        )
        body = self._pedir(db=("unreachable", "No se puede conectar con PostgreSQL."))
        assert body["checks"]["backup"] == "error"
        assert body["status"] == "unhealthy"

    def test_estado_pinta_la_fila_de_copias(self):
        from zascarr.web.routes import TEMPLATES_DIR

        html = (TEMPLATES_DIR / "estado.html").read_text(encoding="utf-8")
        assert 'backup: "Copias de seguridad"' in html
        assert "Copia reciente verificada" in html
        assert "La última copia falló" in html


class TestHealthRestore:
    """#334 B2: la restauración de comprobación se lee del fichero del host."""

    @pytest.fixture(autouse=True)
    def _encendidos(self, clientes):
        clientes()

    def _estado(self, tmp_path, monkeypatch, **datos):
        ruta = tmp_path / "restore-status.json"
        ruta.write_text(json.dumps(datos), encoding="utf-8")
        monkeypatch.setattr(get_settings(), "restore_status_file", str(ruta))
        return ruta

    def _pedir(self, db=("ok", "Conectada y migrada.")):
        with (
            patch("zascarr.api.health._check_transmission", AsyncMock(return_value=True)),
            patch("zascarr.api.health._check_amule", AsyncMock(return_value=True)),
            patch("zascarr.api.health._database_status", AsyncMock(return_value=db)),
            _fake_db_client() as client,
        ):
            return client.get("/api/health").json()

    def test_ok_fresco(self, tmp_path, monkeypatch):
        self._estado(tmp_path, monkeypatch, status="ok", error=None, last_ok_at_epoch=time.time())
        body = self._pedir()
        assert body["checks"]["restore"] == "ok"
        assert body["status"] == "healthy"

    def test_failed_es_error_y_deja_el_global_en_degraded(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path,
            monkeypatch,
            status="failed",
            error="restore_failed",
            last_ok_at_epoch=time.time(),
        )
        body = self._pedir()
        assert body["checks"]["restore"] == "error"
        assert body["status"] == "degraded"
        assert "restauración" in body["warnings"]["restore"].lower()

    def test_warning_por_manifiesto(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path,
            monkeypatch,
            status="warning",
            error="manifest_ausente",
            last_ok_at_epoch=time.time(),
        )
        body = self._pedir()
        assert body["checks"]["restore"] == "warning"
        assert body["status"] == "degraded"
        assert "manifiesto" in body["warnings"]["restore"]

    @pytest.mark.parametrize("dias, esperado", [(40, "warning"), (80, "error")])
    def test_antiguedad_de_la_ultima_restauracion(self, tmp_path, monkeypatch, dias, esperado):
        self._estado(
            tmp_path,
            monkeypatch,
            status="ok",
            error=None,
            last_ok_at_epoch=time.time() - dias * 86400,
        )
        body = self._pedir()
        assert body["checks"]["restore"] == esperado
        assert body["status"] == "degraded"

    def test_fichero_ausente_es_error_sin_500(self, tmp_path, monkeypatch):
        monkeypatch.setattr(get_settings(), "restore_status_file", str(tmp_path / "no-existe.json"))
        body = self._pedir()
        assert body["checks"]["restore"] == "error"
        assert body["status"] == "degraded"
        assert "No hay registro" in body["warnings"]["restore"]

    def test_json_invalido_es_error_sin_500(self, tmp_path, monkeypatch):
        ruta = tmp_path / "restore-status.json"
        ruta.write_text("no es json", encoding="utf-8")
        monkeypatch.setattr(get_settings(), "restore_status_file", str(ruta))
        body = self._pedir()
        assert body["checks"]["restore"] == "error"
        assert body["status"] == "degraded"

    def test_bd_caida_sigue_siendo_unhealthy(self, tmp_path, monkeypatch):
        self._estado(
            tmp_path,
            monkeypatch,
            status="failed",
            error="restore_failed",
            last_ok_at_epoch=time.time(),
        )
        body = self._pedir(db=("unreachable", "No se puede conectar con PostgreSQL."))
        assert body["checks"]["restore"] == "error"
        assert body["status"] == "unhealthy"

    def test_estado_pinta_la_fila_de_restauracion(self):
        from zascarr.web.routes import TEMPLATES_DIR

        html = (TEMPLATES_DIR / "estado.html").read_text(encoding="utf-8")
        assert 'restore: "Restauración"' in html
        assert "Restauración reciente verificada" in html
        assert "La última restauración falló" in html
