"""Verificación real de Comic Vine (#465): una pasada, sin red en tests."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from scripts.medicion import verificar_cv_detalle as modulo
from zascarr.services.comic_vine import CVIssueResult, CVVolume

FIXTURE = Path("/tmp/no-usado")


class _ClienteFalso:
    def __init__(self, *, volumen=None, issue=None):
        self.volumen = volumen
        self.issue = issue
        self.volumen_llamadas = []
        self.issue_llamadas = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None

    async def get_volume(self, volume_id):
        self.volumen_llamadas.append(volume_id)
        return self.volumen

    async def get_issue(self, issue_id):
        self.issue_llamadas.append(issue_id)
        return self.issue


def _volumen():
    return CVVolume(
        cv_id=31306, name="Dragon Ball", publisher="Viz", start_year=2003,
        count_of_issues=16, first_issue={"id": 4000, "issue_number": "1"},
        last_issue={"id": 4016, "issue_number": "16"}, peticiones=1)


def _issue():
    return CVIssueResult(cv_id=4000, issue_number="1", cover_date="2003-01-01")


class TestSinClave:
    def test_sin_ajustes_sale_2_y_no_llama_al_cliente(self, monkeypatch, capsys):
        monkeypatch.setattr(modulo, "cargar_ajustes", AsyncMock(return_value=False))
        creado = []

        def factory():
            creado.append(True)
            raise AssertionError("no se puede construir el cliente sin clave")
        rc = modulo.main(["--volume", "31306", "--salida", "/tmp/x.json"],
                         cliente_factory=factory)
        assert rc == 2 and creado == []
        salida = capsys.readouterr()
        assert "sin_ajustes_o_sin_clave" in salida.out

    def test_sin_clave_configurada_sale_2_y_no_llama(self, monkeypatch, capsys):
        monkeypatch.setattr(modulo, "cargar_ajustes", AsyncMock(return_value=True))
        monkeypatch.setattr(modulo, "get_settings",
                            lambda: SimpleNamespace(comicvine_api_key=""))
        creado = []

        def factory():
            creado.append(True)
            raise AssertionError("no se puede construir el cliente sin clave")
        rc = modulo.main(["--volume", "31306"], cliente_factory=factory)
        assert rc == 2 and creado == []
        assert "sin_clave" in capsys.readouterr().out


class TestVerificacion:
    def test_hace_dos_peticiones_y_sanea_la_salida_y_la_fixture(
            self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(modulo, "cargar_ajustes", AsyncMock(return_value=True))
        monkeypatch.setattr(modulo, "get_settings",
                            lambda: SimpleNamespace(comicvine_api_key="SECRETO"))
        cliente = _ClienteFalso(volumen=_volumen(), issue=_issue())
        salida_path = tmp_path / "comicvine_volume_31306_real.json"
        rc = modulo.main(["--volume", "31306", "--salida", str(salida_path),
                          "--sha-ejecutor", "abc123"],
                         cliente_factory=lambda: cliente)
        assert rc == 0
        assert cliente.volumen_llamadas == [31306]
        assert cliente.issue_llamadas == [4000]       # first_issue del volumen
        salida = capsys.readouterr()
        assert "SECRETO" not in salida.out and "http" not in salida.out.lower()
        assert "Viz" in salida.out and "Dragon Ball" in salida.out

        fixture = json.loads(salida_path.read_text(encoding="utf-8"))
        texto = json.dumps(fixture, ensure_ascii=False)
        assert "SECRETO" not in texto and "http" not in texto.lower()
        assert fixture["capturado"]["sha_ejecutor"] == "abc123"
        assert fixture["capturado"]["fecha"]
        assert fixture["id"] == 31306 and fixture["publisher"] == "Viz"
        assert fixture["first_issue"] == {"id": 4000, "issue_number": "1"}
        assert fixture["issue"]["issue_number"] == "1"

    def test_sin_issue_usa_first_issue_y_no_pide_si_falta(self, monkeypatch, tmp_path):
        monkeypatch.setattr(modulo, "cargar_ajustes", AsyncMock(return_value=True))
        monkeypatch.setattr(modulo, "get_settings",
                            lambda: SimpleNamespace(comicvine_api_key="SECRETO"))
        sin_first = _volumen()
        sin_first = CVVolume(cv_id=1, name="X", publisher=None, first_issue=None)
        cliente = _ClienteFalso(volumen=sin_first)
        rc = modulo.main(["--volume", "1", "--salida", str(tmp_path / "f.json")],
                         cliente_factory=lambda: cliente)
        assert rc == 0
        assert cliente.issue_llamadas == []

    def test_volumen_inexistente_es_estado_sin_resultados(self, monkeypatch, tmp_path, capsys):
        monkeypatch.setattr(modulo, "cargar_ajustes", AsyncMock(return_value=True))
        monkeypatch.setattr(modulo, "get_settings",
                            lambda: SimpleNamespace(comicvine_api_key="clave"))
        cliente = _ClienteFalso(volumen=None)
        rc = modulo.main(["--volume", "9", "--salida", str(tmp_path / "f.json")],
                         cliente_factory=lambda: cliente)
        assert rc == 1
        assert cliente.issue_llamadas == []
        assert "sin_resultados" in capsys.readouterr().out
