# ruff: noqa: E501
"""Persistencia/rotación de logs y visor por fecha, hora y evento."""
from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from zascarr.main import app
from zascarr.services import logs_persistidos
from zascarr.utils.registro_archivo import EscritorJsonl


def _evento(fecha: str, hora: str, evento: str = "prueba.evento", **extra):
    return {"timestamp": f"{fecha}T{hora}:00Z", "level": "info", "event": evento, **extra}


def _ajustes(tmp_path):
    return SimpleNamespace(log_dir=tmp_path / "logs", log_max_bytes=10_000,
                           log_backups=2, log_retention_days=7)


def test_escribe_por_dia_y_filtra_por_fecha_hora_y_evento(tmp_path, monkeypatch):
    class FechaFija(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 17, tzinfo=tz)

    monkeypatch.setattr("zascarr.utils.registro_archivo.datetime", FechaFija)
    escritor = EscritorJsonl(tmp_path / "logs", max_bytes=10_000, backups=2,
                             retencion_dias=7)
    escritor.escribir(_evento("2026-11-17", "10:01", "importer.cycle_done"))
    escritor.escribir(_evento("2026-11-17", "10:02", "cache_http.hit"))
    escritor.escribir(_evento("2026-11-16", "23:59", "importer.cycle_done"))
    ajustes = _ajustes(tmp_path)
    assert [(d["fecha"]) for d in logs_persistidos.dias_disponibles(ajustes)] == [
        "2026-11-17", "2026-11-16"]
    assert [e["event"] for e in logs_persistidos.leer_eventos(
        ajustes, fecha="2026-11-17", hora="10:01")] == ["importer.cycle_done"]
    assert [e["event"] for e in logs_persistidos.leer_eventos(
        ajustes, evento="importer.cycle_done")] == [
        "importer.cycle_done", "importer.cycle_done"]
    assert logs_persistidos.eventos_disponibles(ajustes, fecha="2026-11-17") == [
        "cache_http.hit", "importer.cycle_done"]


def test_rota_por_tamano_y_conserva_backups(tmp_path):
    escritor = EscritorJsonl(tmp_path, max_bytes=1024, backups=2, retencion_dias=7)
    for i in range(20):
        escritor.escribir(_evento("2026-11-17", f"10:{i:02d}", "relleno" + "x" * 80))
    archivos = sorted(p.name for p in tmp_path.glob("*.jsonl"))
    assert "zascarr-2026-11-17.jsonl" in archivos
    assert any(".1.jsonl" in n for n in archivos)
    assert not any(".3.jsonl" in n for n in archivos)


def test_el_visor_y_la_descarga_filtrada_usan_los_ficheros(tmp_path, monkeypatch):
    escritor = EscritorJsonl(tmp_path / "logs", max_bytes=10_000, backups=2,
                             retencion_dias=7)
    escritor.escribir(_evento("2026-11-17", "10:01", "importer.cycle_done",
                              request_id="abc", file_id="f1"))
    escritor.escribir(_evento("2026-11-17", "10:02", "cache_http.hit", file_id="f2"))
    monkeypatch.setattr("zascarr.services.logs_persistidos.get_settings",
                        lambda: _ajustes(tmp_path))

    visor = TestClient(app).get("/ui/logs/visor?fecha=2026-11-17")
    assert visor.status_code == 200
    assert "2026-11-17" in visor.text and "importer.cycle_done" in visor.text
    descarga = TestClient(app).get(
        "/ui/logs?fecha=2026-11-17&hora=10:01&evento=importer.cycle_done")
    assert descarga.status_code == 200
    lineas = [json.loads(x) for x in descarga.text.splitlines() if x]
    assert len(lineas) == 1 and lineas[0]["event"] == "importer.cycle_done"
    assert lineas[0]["request_id"] == "abc"
    assert "attachment;" in descarga.headers["content-disposition"]


def test_sin_ficheros_el_visor_lo_explica(tmp_path, monkeypatch):
    monkeypatch.setattr("zascarr.services.logs_persistidos.get_settings",
                        lambda: _ajustes(tmp_path))
    r = TestClient(app).get("/ui/logs/visor")
    assert r.status_code == 200
    assert "Todavía no hay ficheros" in r.text
