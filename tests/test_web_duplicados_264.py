# ruff: noqa: E501
"""#264 B: UI de apartar duplicados en /ui/auditoria (TestClient, sin PG)."""
from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.apartado_duplicados import (
    ApartadoDuplicadosService,
    ResultadoApartado,
    ResultadoGrupo,
    VistaApartado,
)


class FakeExecResult:
    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value

    def scalars(self):
        return SimpleNamespace(all=lambda: self._value or [])

    def all(self):
        if self._rows is not None:
            return self._rows
        raise AttributeError("sin filas")


class FakeSession:
    def __init__(self, queue=None):
        self.queue = list(queue or [])
        self.added = []

    async def execute(self, _statement):
        return self.queue.pop(0) if self.queue else FakeExecResult(None)

    def add(self, obj):
        self.added.append(obj)


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            async def _get_db():
                yield session
            app.dependency_overrides[get_db] = _get_db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def informe_falso(grupos):
    class Run:
        details = {"kind": "audit", "files_scanned": 10, "files_hashed": 2,
                   "bytes_recuperables": sum(d["size_bytes"] * (len(d["rutas"]) - 1) for d in grupos),
                   "truncado": False, "mismo_contenido": grupos,
                   "misma_obra": [], "carpetas_repetidas": [], "carpetas_vacias": [],
                   "no_reconocidos": []}
        started_at = datetime(2026, 11, 12, tzinfo=UTC)
        files_scanned = 10
    return Run()


def grupo(tmp_path: Path, sha="a" * 64):
    a = tmp_path / "Tebeos" / "Batman 001.cbz"
    b = tmp_path / "Comics" / "Batman 001 (copia).cbz"
    a.parent.mkdir(parents=True, exist_ok=True)
    b.parent.mkdir(parents=True, exist_ok=True)
    a.write_bytes(b"igual")
    b.write_bytes(b"igual")
    return {"sha256": sha, "size_bytes": 5, "rutas": [str(a), str(b)]}


def test_pagina_no_prescosecha_y_muestra_hechos(tmp_path):
    g = grupo(tmp_path)
    with use_fake_session(FakeSession([FakeExecResult(informe_falso([g]))])) as c:
        r = c.get("/ui/auditoria")
    assert r.status_code == 200
    seccion = r.text[r.text.index("Apartar copias idénticas"):]
    assert 'type="radio"' in seccion
    assert "checked" not in seccion
    assert "Batman 001.cbz" in seccion
    assert "No está en el catálogo" in seccion
    assert "Nombre:" in seccion and "Modificado:" in seccion
    assert "Copias apartadas" in seccion
    assert "No se borran automáticamente" in seccion
    assert r.headers["cache-control"] == "no-store"


def test_sin_grupos_no_ofrece_apartar(tmp_path):
    with use_fake_session(FakeSession([FakeExecResult(informe_falso([]))])) as c:
        r = c.get("/ui/auditoria")
    assert r.status_code == 200
    assert "no hay copias idénticas" in r.text.lower()
    assert "Copias apartadas" in r.text


def test_con_catalogo_muestra_serie_y_numero(tmp_path):
    g = grupo(tmp_path)
    fila = SimpleNamespace(file_path=g["rutas"][0], file_name="Batman 001.cbz")
    issue = SimpleNamespace(issue_number="1")
    serie = SimpleNamespace(title="Batman")
    with use_fake_session(FakeSession([
        FakeExecResult(informe_falso([g])),
        FakeExecResult(rows=[(fila, issue, serie)]),
    ])) as c:
        r = c.get("/ui/auditoria")
    assert "Vinculada a «Batman» #1" in r.text


def test_sin_eleccion_no_prepara_nada(tmp_path):
    g = grupo(tmp_path)
    with use_fake_session(FakeSession([FakeExecResult(informe_falso([g]))])) as c:
        r = c.post("/ui/auditoria/duplicados/previsualizar", data={})
    assert r.status_code == 200
    assert "No has elegido" in r.text
    assert "Confirmar y apartar" not in r.text
    assert r.headers["cache-control"] == "no-store"


def test_previsualizar_sin_escribir_y_confirmar_por_grupo(tmp_path, monkeypatch):
    g = grupo(tmp_path)
    async def preview(_self, _sha, rutas, keep):
        return VistaApartado("token-1", "11111111-1111-1111-1111-111111111111",
                             (Path(g["rutas"][0]), Path(g["rutas"][1])), keep, 5)
    monkeypatch.setattr(ApartadoDuplicadosService, "previsualizar", preview)
    with use_fake_session(FakeSession([FakeExecResult(informe_falso([g]))])) as c:
        r = c.post("/ui/auditoria/duplicados/previsualizar",
                   data={f"keep_{g['sha256']}": Path(g["rutas"][0]).name})
    assert r.status_code == 200
    assert "Confirmar y apartar" in r.text
    assert "Se apartarán" in r.text
    m = re.search(r'name="token" value="([^"]+)"', r.text)
    assert m
    gjson = html.unescape(re.search(r'name="grupos" value="([^"]+)"', r.text).group(1))
    async def confirmar(_self, _token, _grupos):
        return ResultadoApartado("11111111-1111-1111-1111-111111111111", "confirmada",
                                 [ResultadoGrupo("a" * 64, "movido", movidos=1, bytes=5)],
                                 1, 1, 5)
    monkeypatch.setattr(ApartadoDuplicadosService, "confirmar", confirmar)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/confirmar",
                   data={"token": "token-1", "grupos": gjson})
    assert r.status_code == 200
    assert "Apartado: 1 archivo" in r.text
    assert "Deshacer el apartado" in r.text


def test_confirmar_rechazado_no_tumba_el_resto(tmp_path, monkeypatch):
    async def confirmar(_self, _token, _grupos):
        return ResultadoApartado("22222222-2222-2222-2222-222222222222", "confirmada",
                                 [ResultadoGrupo("a" * 64, "rechazado", motivo="contenido_cambiado")],
                                 1, 1, 0)
    monkeypatch.setattr(ApartadoDuplicadosService, "confirmar", confirmar)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/confirmar",
                   data={"token": "t", "grupos": '{"sha256":"%s","rutas":["a","b"],"keep_index":0}' % ("a" * 64)})
    assert r.status_code == 200
    print("RESULTHTML", r.text[r.text.index("<main"):])
    assert "No se ha apartado" in r.text
    assert "El contenido de una copia cambió" in r.text


def test_deshacer_ocupado_se_explica_sin_sobrescribir(tmp_path, monkeypatch):
    async def deshacer(_self, _operacion):
        return ResultadoApartado("33333333-3333-3333-3333-333333333333", "confirmada",
                                 [], motivo="sitio_ocupado")
    monkeypatch.setattr(ApartadoDuplicadosService, "deshacer", deshacer)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/deshacer", data={"operacion": "33333333-3333-3333-3333-333333333333"})
    assert r.status_code == 200
    assert "No se ha deshecho" in r.text
    assert "El sitio original está ocupado" in r.text


def test_resultado_rechazado_sin_movimientos_no_dice_listo(monkeypatch):
    async def confirmar(_self, _token, _grupos):
        return ResultadoApartado(
            "44444444-4444-4444-4444-444444444444", "rechazada", [],
            1, 0, 0, motivo="No se ha apartado nada: ninguna copia se pudo mover.")
    monkeypatch.setattr(ApartadoDuplicadosService, "confirmar", confirmar)
    with use_fake_session(FakeSession([])) as c:
        r = c.post("/ui/auditoria/duplicados/confirmar",
                   data={"token": "t", "grupos": '{"sha256":"%s","rutas":["a","b"],"keep_index":0}' % ("a" * 64)})
    assert r.status_code == 200
    assert "Listo" not in r.text
    assert "No se ha apartado nada" in r.text
    assert "Ninguna copia se pudo mover" in r.text
