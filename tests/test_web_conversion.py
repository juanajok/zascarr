# ruff: noqa: E501
"""#478: vista previa, confirmación y deshacer en la ficha (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.conversion import (
    LoteConversion,
    ResultadoConversion,
    ResultadoLote,
    VistaConversion,
)
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
    def __init__(self, vista=None, resultado=None, deshacer=None, lote=None, lote_resultado=None):
        self.vista, self.resultado, self.deshacer_resultado = vista, resultado, deshacer
        self.lote, self.lote_resultado = lote, lote_resultado

    async def previsualizar(self, *_a):
        return self.vista

    async def confirmar(self, _token, *, forzar_compartido=False, **_kw):
        self.forzado = forzar_compartido
        return self.resultado

    async def previsualizar_deshacer(self, *_a):
        return self.vista

    async def deshacer(self, _token, *, forzar_compartido=False, **_kw):
        return self.deshacer_resultado

    async def previsualizar_lote(self, *_a):
        return self.lote

    async def convertir_lote(self, *_a):
        return self.lote_resultado


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
    assert "Convirtiendo" in r.text and "htmx-indicator" in r.text
    # Confirmar por HTMX dentro de la ficha: si no, el navegador acaba en el fragmento suelto.
    assert f'hx-post="/ui/series/{serie.id}/archivos/{servicio.vista.file_id}/convertir"' in r.text
    assert f'hx-target="#conversion-{servicio.vista.file_id}"' in r.text
    assert "parece compartido" in r.text and 'name="forzar_compartido"' in r.text
    assert "El original se aparta y se puede deshacer" in r.text


def test_confirmacion_muestra_resultado_y_enlace_deshacer(monkeypatch):
    serie = _serie()
    r = ResultadoConversion(1, "conversion", str(uuid4()), str(uuid4()), "convertida", None,
                            "Convertida a CBZ.",
                            antes={"ruta": "/lib/Tebeo 01.cbr", "tamano": 1048576},
                            despues={"ruta": "/lib/Tebeo 01.cbz", "tamano": 524288})
    c = _cliente(monkeypatch, _Servicio(resultado=r), serie)
    try:
        respuesta = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir",
                           data={"token": "tok"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert respuesta.status_code == 200
    assert "Convertida a CBZ" in respuesta.text
    assert "ya es un CBZ" in respuesta.text and "Tebeo 01.cbz" in respuesta.text
    assert "MB → " in respuesta.text
    assert f"/archivos/{r.file_id}/convertir/deshacer" in respuesta.text
    assert "Volver a la serie" in respuesta.text
    assert "Duplicados" in respuesta.text


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


def test_errores_de_token_son_400_y_410(monkeypatch):
    from zascarr.services.vinculacion import TokenCaducadoError, TokenInvalidoError

    class _Falla:
        async def confirmar(self, *_a, **_k):
            raise TokenInvalidoError("no vale")

        async def deshacer(self, *_a, **_k):
            raise TokenCaducadoError("caducó", puede_haberse_aplicado=False)

    serie = _serie()
    c = _cliente(monkeypatch, _Falla(), serie)
    try:
        r400 = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir", data={"token": "x"})
        r410 = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir/deshacer",
                      data={"token": "x"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r400.status_code == 400
    assert r410.status_code == 410


def _lote(vistas=()):
    return LoteConversion(str(uuid4()), tuple(vistas), (), (), total_cbr=1,
                          escaneados=1, limite=5)


def test_lote_previa_muestra_convertibles_y_boton(monkeypatch):
    serie = _serie()
    servicio = _Servicio()
    servicio.lote = _lote([_vista()])
    servicio.lote_resultado = ResultadoLote(str(serie.id), 1, 0, (), 5)
    cliente = _cliente(monkeypatch, servicio, serie)

    r = cliente.get(f"/ui/series/{serie.id}/convertir")

    assert r.status_code == 200
    assert "Convertir 1 CBR a CBZ" in r.text
    assert "Tebeo 01.cbr" in r.text
    assert "Convirtiendo la tanda" in r.text and "htmx-indicator" in r.text
    assert f'hx-post="/ui/series/{serie.id}/convertir"' in r.text
    assert 'hx-target="#conversion-lote"' in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_lote_confirmar_muestra_informe_y_la_siguiente_tanda(monkeypatch):
    serie = _serie()
    servicio = _Servicio()
    servicio.lote = _lote([_vista()])
    servicio.lote_resultado = ResultadoLote(
        str(serie.id), 1, 0, (("Tebeo 01.cbr", "Convertida."),), 5)
    cliente = _cliente(monkeypatch, servicio, serie)

    r = cliente.post(f"/ui/series/{serie.id}/convertir")

    assert r.status_code == 200
    assert "Convertidos 1 CBR" in r.text
    assert "Qué ha pasado con cada archivo" in r.text
    assert r.headers["Cache-Control"] == "no-store"


def test_cierre_de_ya_convertida_nombra_el_archivo_y_nunca_el_uuid(monkeypatch):
    serie = _serie()
    uid = uuid4()
    r = ResultadoConversion(1, "conversion", str(uuid4()), str(uid), "ya_convertida", None,
                            "Ya estaba convertida.", repetida=True)
    c = _cliente(monkeypatch, _Servicio(resultado=r), serie)
    try:
        respuesta = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir",
                           data={"token": "tok"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert respuesta.status_code == 200
    assert "el tebeo ya es un CBZ" in respuesta.text
    assert f"«{uid}»" not in respuesta.text  # nunca el UUID como nombre


def test_un_error_de_token_en_htmx_se_avisa_en_la_ficha(monkeypatch):
    from zascarr.services.vinculacion import TokenCaducadoError

    class _Falla:
        async def confirmar(self, *_a, **_k):
            raise TokenCaducadoError("La vista previa caducó.", puede_haberse_aplicado=False)

    serie = _serie()
    c = _cliente(monkeypatch, _Falla(), serie)
    try:
        respuesta = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir",
                           data={"token": "x"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert respuesta.status_code == 200
    assert "La vista previa caducó" in respuesta.text
    assert "Abrir la vista previa de nuevo" in respuesta.text
