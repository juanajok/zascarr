"""UATP-08: la interfaz explica a qué momento vuelve la recuperación (aditivo y saneado)."""
from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.services import ops_host
from zascarr.web.routes import crear_templates

templates = crear_templates()
TS = "backup-20260101_120000"
EPOCH = 1_767_225_600
VERSION = {"head": "a" * 40, "build_sha": "b" * 40, "app_version": "1.15.1", "alembic": "0052"}


def _copia(**extra):
    return {"id": TS, "creada_epoch": EPOCH, "fecha_absoluta": "01/01/2026 a las 13:00",
            "version": VERSION, "tamano": "1,0 MB", "fuera_del_disco": True,
            "verificada": True, "revision": "0052", "restaurable": True, "motivo": "", **extra}


def test_lista_muestra_fecha_absoluta_y_version_sin_hashes():
    html = templates.env.get_template("_copias_items.html").render(
        copias=[_copia()], restaurando=False, oob=False, version_llana=ops_host.version_llana)
    assert "01/01/2026 a las 13:00" in html
    assert "Versión 1.15.1 · revisión 0052" in html
    assert "Las horas son del servidor." in html
    assert "a" * 40 not in html and "b" * 40 not in html
    html2 = templates.env.get_template("_copias_items.html").render(
        copias=[_copia(version=None)], restaurando=False, oob=False,
        version_llana=ops_host.version_llana)
    assert "Versión no consta" in html2


def test_confirmacion_explica_fecha_version_alcance_y_cambios(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    class _DB:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, *_exc):
            return False

    s = get_settings()
    object.__setattr__(s, "auth_mode", "none")
    copia = _copia()
    monkeypatch.setattr("zascarr.web.copias.get_settings", lambda: s)
    monkeypatch.setattr("zascarr.web.copias.ops_host.leer_copias", lambda _s: [copia])
    monkeypatch.setattr("zascarr.web.copias.ops_host.resolver_restauracion",
                        lambda _s: SimpleNamespace(en_marcha=False))
    monkeypatch.setattr("zascarr.web.copias.restauracion.revision_actual",
                        AsyncMock(return_value="0052"))
    monkeypatch.setattr("zascarr.database.async_session_factory", lambda: _DB())
    from zascarr.main import app
    r = TestClient(app).get(f"/ui/copias/restaurar/{TS}")
    assert r.status_code == 200
    assert f"Vas a volver a los datos del {ops_host.fecha_absoluta(EPOCH)}" in r.text
    assert "Versión 1.15.1 · revisión 0052" in r.text
    assert "No contiene los archivos de tu biblioteca" in r.text
    assert "Se pierden los cambios posteriores a esa copia" in r.text
    assert "a" * 40 in r.text  # los hashes solo en el detalle técnico


def _cliente_estado(tmp_path, datos):
    estado = tmp_path / "estado"
    estado.mkdir()
    (estado / "ops-restaurar.json").write_text(json.dumps(datos))
    s = get_settings()
    object.__setattr__(s, "auth_mode", "none")
    object.__setattr__(s, "ops_restaurar_status_file", str(estado / "ops-restaurar.json"))
    object.__setattr__(s, "ops_status_file", str(estado / "ops-status.json"))
    from zascarr.main import app
    return s, TestClient(app)


def test_resumen_hecho_muestra_recuentos_fuera_version_y_comprobaciones(tmp_path, monkeypatch):
    s, c = _cliente_estado(tmp_path, {
        "schema": 1, "copia": TS, "copia_epoch": EPOCH, "resultado": "hecha",
        "actualizado_epoch": 1_800_000_000, "recuentos": {"series": 2, "issues": 3, "files": 4},
        "recuentos_previos": {"series": 3, "issues": 3, "files": 4},
        "version_arrancada": VERSION, "intento": "a1b2c3d4e5f60718",
        "comprobaciones": [{"codigo": "health", "estado": "ok"},
                           {"codigo": "sha256_copia", "estado": "ok"}],
    })
    monkeypatch.setattr("zascarr.web.copias.get_settings", lambda: s)
    r = c.get("/ui/copias/restauracion")
    assert r.status_code == 200
    assert "Copia restaurada" in r.text and "2 series, 3 números y 4 archivos" in r.text
    assert "Antes de restaurar había 3 series" in r.text
    assert "Versión 1.15.1" in r.text
    assert "Queda fuera de la copia" in r.text and "Comprobaciones" in r.text
    assert "a1b2c3d4e5f60718" in r.text and "health: ok" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_resumen_fallo_muestra_identidad_y_proximo_paso(tmp_path, monkeypatch):
    s, c = _cliente_estado(tmp_path, {
        "schema": 1, "copia": TS, "copia_epoch": EPOCH, "resultado": "fallida",
        "error": "sha256_copia", "base_en_su_sitio": True, "recuentos": None,
        "copia_version": VERSION, "intento": "a1b2c3d4e5f60718",
        "comprobacion": "sha256_copia",
    })
    monkeypatch.setattr("zascarr.web.copias.get_settings", lambda: s)
    r = c.get("/ui/copias/restauracion")
    assert r.status_code == 200
    assert "No se pudo restaurar" in r.text
    assert "Tus datos siguen como estaban." in r.text
    assert "Elige otra copia" in r.text
    assert "a1b2c3d4e5f60718" in r.text and "sha256_copia" in r.text


def test_resumen_sin_datos_no_finge_una_restauracion(tmp_path, monkeypatch):
    s, c = _cliente_estado(tmp_path, {})
    monkeypatch.setattr("zascarr.web.copias.get_settings", lambda: s)
    r = c.get("/ui/copias/restauracion")
    assert r.status_code == 200
    assert "No hay ninguna restauración que contar" in r.text


def test_login_enlaza_al_resumen_y_el_health_publica_build_sha(tmp_path, monkeypatch):
    from pathlib import Path
    login = Path("src/zascarr/web/templates/login.html").read_text(encoding="utf-8")
    assert 'href="/login?next=%2Fui%2Fcopias%2Frestauracion"' in login
    s = get_settings()
    monkeypatch.setattr("zascarr.api.health.get_settings", lambda: s)
    object.__setattr__(s, "build_sha", "b" * 40)
    from zascarr.main import app
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.json()["build_sha"] == "b" * 40
