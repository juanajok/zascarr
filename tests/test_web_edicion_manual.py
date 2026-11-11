"""BL-INF5 (#591): formularios de edición manual (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.edicion_manual import ResultadoEdicion


class _Res:
    def __init__(self, filas):
        self._filas = filas

    def scalar_one_or_none(self):
        return self._filas[0] if self._filas else None

    def scalar_one(self):
        return self._filas[0]

    def first(self):
        return self._filas[0] if self._filas else None

    def scalars(self):
        return self

    def all(self):
        return self._filas


class _Sesion:
    def __init__(self, filas):
        self._filas = list(filas)
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.flush = AsyncMock()

    async def execute(self, _s):
        return self._filas.pop(0)


def _serie():
    return SimpleNamespace(id=uuid4(), title="Thorgal", start_year=1980, end_year=None,
                           publisher=None, description=None, total_issues=None,
                           metadata_={}, locked_fields=[], metadata_source="comic_vine")


def _issue(serie):
    return SimpleNamespace(id=uuid4(), series_id=serie.id, issue_number="3", title=None,
                           release_date=None, format=SimpleNamespace(value="single_issue"),
                           synopsis=None, metadata_={}, locked_fields=[],
                           series=serie)


def _cliente(sesion):
    async def _db():
        yield sesion
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_formulario_de_serie_precarga_valores_y_garantia():
    serie = _serie()
    sesion = _Sesion([_Res([serie])])
    c = _cliente(sesion)
    try:
        r = c.get(f"/ui/series/{serie.id}/editar")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'value="Thorgal"' in r.text
    assert "tus archivos no se tocan" in r.text
    assert "Guardar" in r.text


def test_guardar_serie_redirige_con_aviso():
    serie = _serie()
    sesion = _Sesion([_Res([serie])])
    c = _cliente(sesion)
    try:
        with patch("zascarr.web.series.guardar_serie_manual",
                   AsyncMock(return_value=ResultadoEdicion(True, cambios={"title": "X"}))):
            r = c.post(f"/ui/series/{serie.id}/editar", data={
                "title": "Thorgal", "start_year": "1980", "end_year": "",
                "publisher": "", "description": "", "total_issues": ""},
                follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303
    assert r.headers["location"] == f"/ui/series/{serie.id}?guardado=serie"
    sesion.commit.assert_awaited()


def test_error_de_serie_conserva_lo_escrito_sin_422():
    serie = _serie()
    sesion = _Sesion([_Res([serie])])
    c = _cliente(sesion)
    try:
        with patch("zascarr.web.series.guardar_serie_manual",
                   AsyncMock(return_value=ResultadoEdicion(
                       False, {"title": "El título no puede estar vacío."}))):
            r = c.post(f"/ui/series/{serie.id}/editar", data={
                "title": "", "start_year": "", "end_year": "",
                "publisher": "", "description": "", "total_issues": ""})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "El título no puede estar vacío" in r.text
    sesion.rollback.assert_awaited()


def test_formulario_de_numero_y_guardado():
    serie = _serie()
    issue = _issue(serie)
    sesion = _Sesion([_Res([(issue, serie)]), _Res([(issue, serie)])])
    c = _cliente(sesion)
    try:
        with patch("zascarr.web.series.guardar_numero_manual",
                   AsyncMock(return_value=ResultadoEdicion(True, cambios={"issue_number": "4"}))):
            g = c.get(f"/ui/series/{serie.id}/numero/{issue.id}/editar")
            p = c.post(f"/ui/series/{serie.id}/numero/{issue.id}/editar", data={
                "issue_number": "4", "title": "", "release_date": "",
                "format": "single_issue", "synopsis": ""}, follow_redirects=False)
    finally:
        _cerrar()
    assert g.status_code == 200 and "Editar el número" in g.text
    assert p.status_code == 303
    assert p.headers["location"].endswith("?guardado=numero")


def test_desbloquear_serie_redirige():
    serie = _serie()
    sesion = _Sesion([])
    c = _cliente(sesion)
    try:
        with patch("zascarr.web.series.desbloquear_serie", AsyncMock(return_value=True)):
            r = c.post(f"/ui/series/{serie.id}/editar/desbloquear/title",
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and "guardado=desbloqueado" in r.headers["location"]
