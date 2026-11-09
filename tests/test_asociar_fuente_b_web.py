# ruff: noqa: E501
"""#129 B: B2 y procedencia H12, sin red."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.asociacion_fuente import ResultadoAsociacion
from zascarr.services.procedencia import procedencia_de_serie
from zascarr.services.tokens_revision import AsociacionFirmada, crear_token_asociacion
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
                           gcd_id=None, metadata_={}, locked_fields=[],
                           metadata_source="comic_vine", description=None,
                           cover_url=None, total_issues=None,
                           enrichment_attempted_at=None)


def _settings():
    return SimpleNamespace(secret_key="x" * 32, comicvine_enabled=True,
                           anilist_enabled=True, tebeosfera_enabled=True,
                           gcd_enabled=True, comicvine_api_key="clave")


def _resultado(resultado="asociada", motivo=None, mensaje="Ficha asociada. Si repites esta confirmación, no se duplica."):
    return ResultadoAsociacion(version=1, tipo="asociar_fuente", operacion_id=str(uuid4()),
                               series_id=str(uuid4()), resultado=resultado, motivo=motivo,
                               mensaje=mensaje, fuente="gcd", id_externo="123",
                               aviso=None, otra_serie=None,
                               titulo="The Wicked + The Divine")


class _FakeServicio:
    def __init__(self, resultado):
        self._resultado = resultado

    def __call__(self, *_a, **_k):
        return self

    async def confirmar(self, _token, *, serie_esperada=None):
        self.serie_esperada = serie_esperada
        return self._resultado


def test_b2_exito_con_no_store(monkeypatch):
    serie = _serie()
    servicio = _FakeServicio(_resultado())
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "AsociacionDeFuente", servicio)

    async def _db():
        yield _FakeSession(serie)
    app.dependency_overrides[get_db] = _db
    try:
        r = TestClient(app).post(f"/ui/series/{serie.id}/asociar/confirmar",
                                 data={"token": "x" * 10})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Ficha asociada" in r.text and "no se duplica" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_b2_conflicto_nombra_la_otra_serie(monkeypatch):
    serie = _serie()
    res = _resultado("omitida", "conflicto_identificador")
    res.otra_serie = "Otra serie"
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "AsociacionDeFuente", _FakeServicio(res))

    async def _db():
        yield _FakeSession(serie)
    app.dependency_overrides[get_db] = _db
    try:
        r = TestClient(app).post(f"/ui/series/{serie.id}/asociar/confirmar",
                                 data={"token": "x" * 10})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert "Ficha ocupada" in r.text and "Otra serie" in r.text


def test_h12_dos_fuentes_sin_ids_internos():
    serie = _serie()
    serie.gcd_id = 77
    serie.metadata_ = {
        "asociaciones": [
            {"version": 1, "fuente": "comic_vine", "id_externo": "1", "entidad": "serie",
             "kind": None, "fecha": "2026-11-09T10:00:00+00:00", "operacion_id": str(uuid4()),
             "origen": "confirmada", "modo": "busqueda"},
            {"version": 1, "fuente": "gcd", "id_externo": "77", "entidad": "serie",
             "kind": None, "fecha": "2026-11-09T11:00:00+00:00", "operacion_id": str(uuid4()),
             "origen": "confirmada", "modo": "busqueda"},
        ]
    }
    proc = procedencia_de_serie(serie)
    assert [i.fuente for i in proc.identidades] == ["Comic Vine", "GCD"]
    assert all(i.fecha for i in proc.identidades)
    assert "1" not in {i.fuente for i in proc.identidades}


class _FakeServicioError(_FakeServicio):
    def __init__(self, exc):
        super().__init__(None)
        self._exc = exc

    async def confirmar(self, _token, *, serie_esperada=None):
        self.serie_esperada = serie_esperada
        raise self._exc


def _post_confirmar(monkeypatch, servicio, serie):
    monkeypatch.setattr(web, "get_settings", _settings)
    monkeypatch.setattr(web, "AsociacionDeFuente", lambda *_a, **_k: servicio)

    async def _db():
        yield _FakeSession(serie)
    app.dependency_overrides[get_db] = _db
    try:
        return TestClient(app).post(f"/ui/series/{serie.id}/asociar/confirmar",
                                    data={"token": "x" * 10})
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_b2_pasa_la_serie_de_la_url_al_servicio(monkeypatch):
    serie = _serie()
    servicio = _FakeServicio(_resultado())
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 200
    assert servicio.serie_esperada == serie.id


def test_b2_token_de_otra_serie_explica_y_no_asocia(monkeypatch):
    from zascarr.services.vinculacion import TokenInvalidoError

    serie = _serie()
    servicio = _FakeServicioError(TokenInvalidoError(
        "La propuesta pertenece a otra serie; no se ha asociado nada."))
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 400
    assert "otra serie" in r.text and "no se ha asociado nada" in r.text


def test_b2_token_invalido_da_400_sin_escribir(monkeypatch):
    from zascarr.services.vinculacion import TokenInvalidoError

    serie = _serie()
    servicio = _FakeServicioError(TokenInvalidoError("La propuesta no es válida: vuelve a buscarla."))
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 400 and "no es válida" in r.text


def test_b2_resultado_incierto_da_503(monkeypatch):
    from zascarr.services.vinculacion import ResultadoInciertoError

    serie = _serie()
    servicio = _FakeServicioError(ResultadoInciertoError("No se sabe si se guardó."))
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 503
    assert "No sabemos" in r.text or "no se sabe" in r.text.lower()


def test_b2_caducado_muestra_el_mensaje_sin_afirmar_lo_que_no_sabe(monkeypatch):
    serie = _serie()
    res = _resultado(
        "omitida", "token_caducado",
        mensaje=("Han pasado más de 15 minutos y ya no se conserva el registro de esta "
                 "operación: no se puede saber si llegó a asociarse."))
    servicio = _FakeServicio(res)
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 200
    assert "no se puede saber" in r.text
    assert "No se ha cambiado nada" not in r.text


def test_b2_ya_asociada_muestra_el_estado_sin_escribir(monkeypatch):
    serie = _serie()
    servicio = _FakeServicio(_resultado("ya_asociada"))
    r = _post_confirmar(monkeypatch, servicio, serie)
    assert r.status_code == 200 and "Ya estaba asociada" in r.text
    assert "No se ha cambiado nada" in r.text


def test_b2_token_real_de_otra_serie_no_llega_al_servicio_ni_escribe(monkeypatch):
    serie = _serie()
    otra = uuid4()
    token = crear_token_asociacion(AsociacionFirmada(
        version=1, entidad="serie", kind="collection", fuente="gcd", id_externo="123",
        titulo="The Wicked + The Divine", anio=2014,
        sitio_url="https://www.comics.org/series/123/", huella="a" * 64,
        operacion=str(uuid4()), serie_id=str(otra)), _settings().secret_key)
    llamadas = []

    class _FakeSesionEspia(_FakeSession):
        async def execute(self, stmt):
            llamadas.append(stmt)
            return await super().execute(stmt)

    monkeypatch.setattr(web, "get_settings", _settings)

    async def _db():
        yield _FakeSesionEspia(serie)
    app.dependency_overrides[get_db] = _db
    try:
        r = TestClient(app).post(f"/ui/series/{serie.id}/asociar/confirmar",
                                 data={"token": token})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 400 and "otra serie" in r.text
    # Solo la lectura de la serie de la URL; el servicio ni siquiera llega a la transacción.
    assert llamadas and all(stmt.__class__.__name__ == "Select" for stmt in llamadas)
