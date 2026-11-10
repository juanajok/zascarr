# ruff: noqa: E501
"""#480: vista previa y resultado de ComicInfo en la ficha (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.core.comicinfo_write import Accion, CampoPlan
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.comicinfo_ficha import ResultadoComicInfo, VistaComicInfo
from zascarr.web import series as web


class _Sesion:
    def __init__(self, serie):
        self._serie = serie

    async def get(self, _modelo, _id):
        return self._serie


def _serie():
    return SimpleNamespace(id=uuid4(), title="Thorgal")


def _vista(**kw):
    campos = [CampoPlan("Series", Accion.CAMBIA, None, "Thorgal"),
              CampoPlan("Number", Accion.YA_COINCIDE, "1", "1")]
    datos = dict(file_id=str(uuid4()), serie_id=str(uuid4()), nombre="Tebeo 01.cbz",
                 es_cbr=False, puede_aplicar=True, motivo=None,
                 mensaje="Revisa los cambios y guarda.", campos=campos,
                 advertencia=None, forzable=False, token="tok")
    datos.update(kw)
    return VistaComicInfo(**datos)


class _Servicio:
    def __init__(self, vista=None, resultado=None):
        self.vista, self.resultado = vista, resultado

    async def previsualizar(self, *_a):
        return self.vista

    async def aplicar(self, _token, **_kw):
        return self.resultado


def _cliente(monkeypatch, servicio, serie):
    async def _db():
        yield _Sesion(serie)
    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(web, "ComicInfoFichaService", lambda *_a, **_k: servicio)
    return TestClient(app)


def test_previa_muestra_campos_token_y_guardar(monkeypatch):
    serie = _serie()
    c = _cliente(monkeypatch, _Servicio(vista=_vista()), serie)
    try:
        r = c.get(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Series" in r.text and "Thorgal" in r.text
    assert 'name="token"' in r.text and "Guardar información en el tebeo" in r.text
    assert 'hx-post="/ui/series/' in r.text and 'hx-target="#comicinfo-' in r.text
    assert "Guardando…" in r.text


def test_previa_compartida_pide_confirmacion(monkeypatch):
    serie = _serie()
    c = _cliente(monkeypatch, _Servicio(vista=_vista(
        advertencia="Cuidado: parece compartido.", forzable=True)), serie)
    try:
        r = c.get(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert "parece compartido" in r.text and 'name="forzar_compartido"' in r.text


def test_cbr_remite_a_conversion(monkeypatch):
    serie = _serie()
    c = _cliente(monkeypatch, _Servicio(vista=_vista(
        es_cbr=True, puede_aplicar=False, token=None,
        mensaje="Es un CBR: conviértelo primero a CBZ.")), serie)
    try:
        r = c.get(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert "conviértelo primero" in r.text
    assert f"/archivos/{_vista().file_id}/convertir" not in r.text  # id distinto: no importa
    assert "/convertir" in r.text


def test_resultado_guardado(monkeypatch):
    serie = _serie()
    resultado = ResultadoComicInfo(1, "comicinfo", str(uuid4()), str(uuid4()), "guardado",
                                   None, "ComicInfo guardado en el tebeo.")
    c = _cliente(monkeypatch, _Servicio(resultado=resultado), serie)
    try:
        r = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo",
                   data={"token": "tok"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "<!doctype html>" in r.text  # sin HTMX, página completa, no un fragmento suelto
    assert "Listo: la información ya está guardada dentro del tebeo." in r.text
    assert "Revisar otra vez" in r.text and "Volver a la serie" in r.text
    assert "Cuidado: este archivo parece compartido" not in r.text


def test_ficha_de_serie_muestra_actualizar_comicinfo_en_cbz():
    from tests.test_web_series import (
        FakeExecResult,
        FakeSession,
        acuse,
        make_series,
        retirados,
        use_fake_session,
    )
    from zascarr.models import FileFormat, IssueFormat

    serie = make_series(total_issues=1)
    archivo = SimpleNamespace(
        id=uuid4(), file_name="Tebeo 01.cbz", file_format=FileFormat.CBZ, is_missing=False,
        metadata_source="manual", metadata_={}, issue_id=uuid4(), issue_number="1",
        sort_order=1.0, series_id=serie.id, format=IssueFormat.SINGLE_ISSUE)
    session = FakeSession([FakeExecResult([serie]), FakeExecResult([]), acuse(), retirados(),
                           FakeExecResult([archivo]), FakeExecResult([])], series=serie)
    with use_fake_session(session) as c:
        r = c.get(f"/ui/series/{serie.id}")
    assert "Actualizar ComicInfo" in r.text
    assert f"/archivos/{archivo.id}/comicinfo" in r.text


def test_errores_token_400_410_llevan_no_store(monkeypatch):
    from zascarr.services.vinculacion import TokenCaducadoError, TokenInvalidoError

    class _Falla:
        async def aplicar(self, *_a, **_k):
            raise TokenInvalidoError("no vale")

    serie = _serie()
    c = _cliente(monkeypatch, _Falla(), serie)
    try:
        r400 = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo",
                      data={"token": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r400.status_code == 400
    assert r400.headers.get("cache-control") == "no-store"

    class _Caduca(_Falla):
        async def aplicar(self, *_a, **_k):
            raise TokenCaducadoError("caducó", puede_haberse_aplicado=False)

    c = _cliente(monkeypatch, _Caduca(), serie)
    try:
        r410 = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo",
                      data={"token": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r410.status_code == 410
    assert r410.headers.get("cache-control") == "no-store"


def test_resultado_htmx_es_solo_el_fragmento(monkeypatch):
    serie = _serie()
    resultado = ResultadoComicInfo(1, "comicinfo", str(uuid4()), str(uuid4()), "guardado",
                                   None, "ComicInfo guardado en el tebeo.")
    c = _cliente(monkeypatch, _Servicio(resultado=resultado), serie)
    try:
        r = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo",
                   data={"token": "tok"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "<!doctype html>" not in r.text
    assert 'class="comicinfo-resultado"' in r.text
    assert "Listo: la información" in r.text


def test_resultado_forzado_no_repite_el_aviso_de_compartido(monkeypatch):
    serie = _serie()
    resultado = ResultadoComicInfo(1, "comicinfo", str(uuid4()), str(uuid4()), "guardado",
                                   None, "ComicInfo guardado en el tebeo.",
                                   campos=[CampoPlan("Series", Accion.CAMBIA, None, "Thorgal")],
                                   advertencia="Cuidado: este archivo parece compartido.",
                                   forzado_compartido=True)
    c = _cliente(monkeypatch, _Servicio(resultado=resultado), serie)
    try:
        r = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/comicinfo",
                   data={"token": "tok"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert "Se guardó con tu confirmación porque el archivo parecía compartido." in r.text
    assert "Cuidado: este archivo parece compartido" not in r.text
    assert "Qué se ha escrito" in r.text and "Thorgal" in r.text
