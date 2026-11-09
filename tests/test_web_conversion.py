# ruff: noqa: E501
"""#478: vista previa, confirmación y deshacer en la ficha (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.conversion import ResultadoConversion, VistaConversion
from zascarr.web import series as web


class _Sesion:
    def __init__(self, serie):
        self._serie = serie

    async def get(self, _modelo, _id):
        return self._serie


def _serie():
    return SimpleNamespace(id=uuid4(), title="Thorgal", metadata_={}, metadata_source="comic_vine",
                           total_issues=1, tradition=None, publisher=None)


def _vista(**kw):
    datos = dict(file_id=str(uuid4()), serie_id=str(uuid4()), nombre_original="Tebeo 01.cbr",
                 nombre_nuevo="Tebeo 01.cbz", metodo="recomprimir", tamano_entrada=1024,
                 estimado_salida=2048, espacio_libre=None, necesario=2048,
                 puede_convertir=True, motivo=None, mensaje="Se puede convertir.", token="tok")
    datos.update(kw)
    return VistaConversion(**datos)


class _Servicio:
    def __init__(self, vista=None, resultado=None, deshacer=None):
        self.vista, self.resultado, self.deshacer_resultado = vista, resultado, deshacer

    async def previsualizar(self, *_a):
        return self.vista

    async def confirmar(self, _token, *, forzar_compartido=False):
        self.forzado = forzar_compartido
        return self.resultado

    async def previsualizar_deshacer(self, *_a):
        return self.vista

    async def deshacer(self, _token, *, forzar_compartido=False):
        return self.deshacer_resultado


def _override(serie):
    async def _db():
        yield _Sesion(serie)
    app.dependency_overrides[get_db] = _db


def _cliente(monkeypatch, servicio, serie):
    _override(serie)
    monkeypatch.setattr(web, "ConversionDeArchivo", lambda *_a, **_k: servicio)
    return TestClient(app)


def test_vista_previa_muestra_garantia_y_token(monkeypatch):
    serie = _serie()
    servicio = _Servicio(vista=_vista(advertencia="Cuidado: parece compartido.", forzable=True))
    c = _cliente(monkeypatch, servicio, serie)
    try:
        r = c.get(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Tebeo 01.cbr" in r.text and "Tebeo 01.cbz" in r.text
    assert 'name="token"' in r.text and "Convertir a CBZ" in r.text
    assert "parece compartido" in r.text and 'name="forzar_compartido"' in r.text
    assert "El original se aparta y se puede deshacer" in r.text


def test_confirmacion_muestra_resultado_y_enlace_deshacer(monkeypatch):
    serie = _serie()
    r = ResultadoConversion(1, "conversion", str(uuid4()), str(uuid4()), "convertida", None,
                            "Convertida a CBZ.")
    c = _cliente(monkeypatch, _Servicio(resultado=r), serie)
    try:
        respuesta = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir",
                           data={"token": "tok"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert respuesta.status_code == 200
    assert "Convertida a CBZ" in respuesta.text
    assert f"/archivos/{r.file_id}/convertir/deshacer" in respuesta.text


def test_ficha_muestra_convertir_para_cbr():
    from tests.test_web_series import (
        FakeExecResult,
        FakeSession,
        acuse,
        make_series,
        retirados,
        use_fake_session,
    )

    serie = make_series(total_issues=1)
    from zascarr.models import FileFormat, IssueFormat

    archivo = SimpleNamespace(
        id=uuid4(), file_name="Tebeo 01.cbr", file_format=FileFormat.CBR, is_missing=False,
        metadata_source="manual", metadata_={}, issue_id=uuid4(), issue_number="1",
        sort_order=1.0, series_id=serie.id, format=IssueFormat.SINGLE_ISSUE)
    session = FakeSession([FakeExecResult([serie]), FakeExecResult([]), acuse(), retirados(),
                           FakeExecResult([archivo]), FakeExecResult([])], series=serie)
    with use_fake_session(session) as c:
        r = c.get(f"/ui/series/{serie.id}")
    assert r.status_code == 200
    assert f"/archivos/{archivo.id}/convertir" in r.text
    assert "Convertir a CBZ" in r.text


def test_deshacer_previa_y_resultado(monkeypatch):
    serie = _serie()
    vista = _vista(nombre_original="Tebeo 01.cbz", nombre_nuevo="Tebeo 01.cbr", token="tok")
    resultado = ResultadoConversion(1, "conversion", str(uuid4()), str(uuid4()), "revertida",
                                    None, "Original restaurado.")
    servicio = _Servicio(vista=vista, deshacer=resultado)
    c = _cliente(monkeypatch, servicio, serie)
    try:
        previa = c.get(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir/deshacer")
        confirmado = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir/deshacer",
                            data={"token": "tok"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert previa.status_code == 200 and "Deshacer la conversión" in previa.text
    assert confirmado.status_code == 200 and "Original restaurado" in confirmado.text
