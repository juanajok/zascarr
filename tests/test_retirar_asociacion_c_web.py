"""#129 C: C1/C2 y no-store, sin red."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.retirar_asociacion import (
    MENSAJE_CADUCADO_SIN_INFORME,
    ResultadoRetirarAsociacion,
    VistaPreviaRetirar,
    huella_de_asociacion_actual,
)
from zascarr.services.tokens_revision import (
    RetirarAsociacionFirmada,
    crear_token_retirar_asociacion,
)
from zascarr.web import asociar_fuente as web


class _FakeSession:
    def __init__(self, serie):
        self._serie = serie

    async def execute(self, _s):
        r = MagicMock()
        r.scalar_one_or_none = MagicMock(return_value=self._serie)
        return r


def _serie():
    return SimpleNamespace(id=uuid4(), title="The Wicked + The Divine", start_year=2014,
                           comic_vine_id=1, anilist_id=None, tebeosfera_slug=None,
                           gcd_id=123, metadata_={}, locked_fields=[],
                           metadata_source="comic_vine")


def _settings():
    return SimpleNamespace(secret_key="x" * 32, comicvine_enabled=True,
                           anilist_enabled=True, tebeosfera_enabled=True,
                           gcd_enabled=True, comicvine_api_key="clave")


class _Servicio:
    def __init__(self, previa=None, resultado=None):
        self.previa = previa
        self.resultado = resultado

    def __call__(self, *_a, **_k):
        return self

    async def previsualizar(self, _sid, _fuente):
        return self.previa

    async def confirmar(self, _token, *, serie_esperada=None):
        self.serie_esperada = serie_esperada
        return self.resultado


class _ServicioError(_Servicio):
    def __init__(self, exc):
        super().__init__()
        self._exc = exc

    async def confirmar(self, _token, *, serie_esperada=None):
        self.serie_esperada = serie_esperada
        raise self._exc


def _override(serie):
    async def _db():
        yield _FakeSession(serie)
    app.dependency_overrides[get_db] = _db


def test_c1_muestra_garantia_y_no_store(monkeypatch):
    serie = _serie()
    previa = VistaPreviaRetirar(
        str(serie.id), serie.title, "gcd", "123", 2014, "2026-11-09",
        "registrada", "ok", "Vas a quitar la ficha.", "token")
    servicio = _Servicio(previa=previa)
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "RetirarAsociacionDeFuente", servicio)
    _override(serie)
    try:
        r = TestClient(app).get(f"/ui/series/{serie.id}/asociar/gcd/retirar")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Retirar la asociación" in r.text
    assert "La serie, sus números y tus archivos siguen igual. Queda en el historial." in r.text
    assert 'name="token"' in r.text
    assert r.headers["cache-control"] == "no-store"


def test_c2_resultado_retirada(monkeypatch):
    serie = _serie()
    resultado = ResultadoRetirarAsociacion(
        version=1, tipo="retirar_asociacion", operacion_id=str(uuid4()),
        series_id=str(serie.id), resultado="retirada", motivo=None,
        mensaje="retirada", fuente="gcd", id_externo="123")
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "RetirarAsociacionDeFuente", _Servicio(resultado=resultado))
    _override(serie)
    try:
        r = TestClient(app).post(f"/ui/series/{serie.id}/asociar/retirar/confirmar",
                                 data={"token": "x" * 10})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Asociación retirada" in r.text
    assert "No se ha cambiado nada" not in r.text
    assert r.headers["cache-control"] == "no-store"


def _post_confirmar(monkeypatch, servicio, serie):
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "RetirarAsociacionDeFuente", lambda *_a, **_k: servicio)
    _override(serie)
    try:
        return TestClient(app).post(f"/ui/series/{serie.id}/asociar/retirar/confirmar",
                                    data={"token": "x" * 10})
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_c2_token_de_otra_serie_explica_y_no_retira(monkeypatch):
    from zascarr.services.vinculacion import TokenInvalidoError

    serie = _serie()
    servicio = _ServicioError(TokenInvalidoError(
        "La propuesta pertenece a otra serie; no se ha retirado nada."))
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 400 and "otra serie" in r.text


def test_c2_resultado_incierto_da_503(monkeypatch):
    from zascarr.services.vinculacion import ResultadoInciertoError

    serie = _serie()
    r = _post_confirmar(monkeypatch, _ServicioError(
        ResultadoInciertoError("No se sabe si se retiró.")), serie)
    assert r.status_code == 503 and "No sabemos" in r.text


def test_c2_token_invalido_da_400(monkeypatch):
    from zascarr.services.vinculacion import TokenInvalidoError

    serie = _serie()
    r = _post_confirmar(monkeypatch, _ServicioError(
        TokenInvalidoError("La propuesta no es válida: vuelve a revisar la ficha.")), serie)
    assert r.status_code == 400 and "no es válida" in r.text


def test_c2_caducado_muestra_el_mensaje_sin_afirmar_lo_que_no_sabe(monkeypatch):
    serie = _serie()
    res = ResultadoRetirarAsociacion(
        version=1, tipo="retirar_asociacion", operacion_id=str(uuid4()),
        series_id=str(serie.id), resultado="omitida", motivo="token_caducado",
        mensaje=MENSAJE_CADUCADO_SIN_INFORME, fuente="gcd", id_externo="123")
    r = _post_confirmar(monkeypatch, _Servicio(resultado=res), serie)
    assert r.status_code == 200 and "no se puede saber" in r.text
    assert "No se ha cambiado nada" not in r.text


def test_token_real_de_otra_serie_no_llega_al_servicio_ni_escribe(monkeypatch):
    serie = _serie()
    otra = SimpleNamespace(id=uuid4(), title="Otra", start_year=2000, comic_vine_id=2,
                           anilist_id=None, tebeosfera_slug=None, gcd_id=123,
                           metadata_={}, locked_fields=[], metadata_source="comic_vine")
    token = crear_token_retirar_asociacion(RetirarAsociacionFirmada(
        version=1, entidad="serie", fuente="gcd", id_externo="123",
        huella=huella_de_asociacion_actual(otra, "gcd"),
        operacion=str(uuid4()), serie_id=str(otra.id)), _settings().secret_key)
    monkeypatch.setattr(web, "get_settings", _settings)
    llamadas = []

    class _FakeSesionEspia(_FakeSession):
        async def execute(self, stmt):
            llamadas.append(stmt)
            return await super().execute(stmt)

    async def _db():
        yield _FakeSesionEspia(serie)
    app.dependency_overrides[get_db] = _db
    try:
        r = TestClient(app).post(f"/ui/series/{serie.id}/asociar/retirar/confirmar",
                                 data={"token": token})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 400 and "otra serie" in r.text
    assert llamadas and all(stmt.__class__.__name__ == "Select" for stmt in llamadas)


def test_ficha_muestra_el_enlace_retirar_con_la_clave_de_la_fuente():
    from tests.test_web_series import (
        FakeExecResult,
        FakeSession,
        acuse,
        make_series,
        retirados,
        use_fake_session,
    )

    serie = make_series(total_issues=1)
    serie.comic_vine_id = 1
    serie.gcd_id = 123
    serie.metadata_ = {"asociaciones": [{
        "version": 1, "fuente": "gcd", "id_externo": "123", "entidad": "serie",
        "kind": None, "fecha": "2026-11-09T10:00:00+00:00",
        "operacion_id": str(uuid4()), "origen": "confirmada", "modo": "busqueda"}]}
    session = FakeSession([
        FakeExecResult([serie]), FakeExecResult([]), acuse(), retirados(), FakeExecResult([]),
    ], series=serie)
    with use_fake_session(session) as client:
        r = client.get(f"/ui/series/{serie.id}")
    assert r.status_code == 200
    assert f'href="/ui/series/{serie.id}/asociar/gcd/retirar"' in r.text
