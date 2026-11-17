"""BL-ETQ1a: panel, alta y baja de etiquetas en la ficha (FakeSession)."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series
from zascarr.services.etiquetas import ResultadoEtiqueta
from zascarr.web import series as web_series


class FakeSession:
    def __init__(self, series):
        self.series = series
        self.flush = AsyncMock()

    async def get(self, _model, _id):
        return self.series


def use_session(series):
    async def _db():
        yield FakeSession(series)

    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = _db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)

    return _Ctx()


def test_panel_y_alta_manual(monkeypatch):
    series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    class Tag:
        name = "noir"
    monkeypatch.setattr(web_series, "etiquetas_de_serie", AsyncMock(return_value=[Tag()]))
    monkeypatch.setattr(web_series, "ideas_para_empezar", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "anadir_etiqueta", AsyncMock(
        return_value=ResultadoEtiqueta(None, "Etiqueta añadida.", True)))
    with use_session(series) as client:
        r = client.get(f"/ui/series/{series.id}/etiquetas")
        assert r.status_code == 200 and "noir" in r.text
        assert "Cache-Control" in r.headers and r.headers["Cache-Control"] == "no-store"
        r2 = client.post(f"/ui/series/{series.id}/etiquetas", data={"etiqueta": "noir"})
    assert r2.status_code == 200 and "Etiqueta añadida." in r2.text


def test_alta_invalida_muestra_aviso_sin_500(monkeypatch):
    series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(web_series, "etiquetas_de_serie", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "ideas_para_empezar", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "anadir_etiqueta", AsyncMock(
        side_effect=web_series.EtiquetaInvalida("Escribe al menos una letra o un número.")))
    with use_session(series) as client:
        r = client.post(f"/ui/series/{series.id}/etiquetas", data={"etiqueta": "!"})
    assert r.status_code == 200
    assert "Escribe al menos una letra" in r.text


def test_sugerencias_vacias_no_consultan(monkeypatch):
    series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(web_series, "etiquetas_de_serie", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "ideas_para_empezar", AsyncMock(return_value=[]))
    with use_session(series) as client:
        r = client.get(f"/ui/series/{series.id}/etiquetas/sugerir?etiqueta=")
    assert r.status_code == 200 and r.text == ""


def test_post_sin_etiqueta_no_da_422_crudo(monkeypatch):
    """Un formulario sin el campo (o con una petición manipulada) no enseña JSON de validación."""
    series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(web_series, "etiquetas_de_serie", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "ideas_para_empezar", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "anadir_etiqueta", AsyncMock(
        side_effect=web_series.EtiquetaInvalida("Escribe al menos una letra o un número.")))
    with use_session(series) as client:
        r = client.post(f"/ui/series/{series.id}/etiquetas")
    assert r.status_code == 200
    assert "Escribe al menos una letra" in r.text
    assert '"detail"' not in r.text


def test_panel_muestra_ideas_para_empezar_sin_asignarlas(monkeypatch):
    from types import SimpleNamespace
    series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
    monkeypatch.setattr(web_series, "etiquetas_de_serie", AsyncMock(return_value=[]))
    monkeypatch.setattr(web_series, "ideas_para_empezar", AsyncMock(
        return_value=[SimpleNamespace(name="noir")]))
    with use_session(series) as client:
        r = client.get(f"/ui/series/{series.id}/etiquetas")
    assert r.status_code == 200
    assert "Ideas para empezar" in r.text and "noir" in r.text
