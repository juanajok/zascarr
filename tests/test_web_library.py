"""
tests/test_web_library.py

Suite de la biblioteca (C1) — /ui/biblioteca. Contrato HTTP, mismo
patrón que test_pendientes.py; la lógica de filtrado ya está cubierta
en test_series_service.py.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from secuenciarr.database import get_db
from secuenciarr.main import app
from secuenciarr.models import ComicTradition, Publisher, Series


class FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def all(self):
        return self._value


class FakeExecResult:
    def __init__(self, value):
        self._value = value

    def scalars(self):
        return FakeScalarResult(self._value)

    def scalar(self):
        return self._value


class FakeSession:
    def __init__(self, queue: list):
        self._queue = list(queue)

    async def execute(self, _statement):
        return self._queue.pop(0)


def override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def make_series(title="Batman") -> Series:
    return Series(id=uuid4(), title=title, tradition=ComicTradition.AMERICAN, start_year=2011)


class TestIndex:

    def test_pagina_lista_series(self):
        series = make_series("Batman")
        session = FakeSession([
            FakeExecResult([]),        # list_publishers_with_series
            FakeExecResult(1),         # count
            FakeExecResult([series]),  # items
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert "Batman" in r.text

    def test_pagina_vacia_muestra_mensaje(self):
        session = FakeSession([
            FakeExecResult([]),
            FakeExecResult(0),
            FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert "Ninguna serie coincide" in r.text


class TestResultados:

    def test_fragmento_con_filtro_de_tradicion(self):
        series = make_series("Thorgal")
        session = FakeSession([FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=franco_belgian")
        assert r.status_code == 200
        assert "Thorgal" in r.text
        # Es un fragmento: no repite el layout completo (topnav).
        assert "SecuenciArr" not in r.text

    def test_campos_uuid_vacios_no_dan_422(self):
        """Regresión: el formulario de filtros manda publisher_id/
        character_id/story_arc_id como "" (campos ocultos sin valor)
        cuando no hay selección — no ausentes de la query string. Un
        UUID | None de FastAPI no acepta "" y daba 422 antes de este fix,
        encontrado probando en un navegador real, no con estos mocks."""
        series = make_series("Batman")
        session = FakeSession([FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get(
                "/ui/biblioteca/resultados"
                "?tradition=american&publisher_id=&character_id=&story_arc_id=&q="
            )
        assert r.status_code == 200
        assert "Batman" in r.text


class TestBuscarPersonajeYSaga:

    def test_buscar_personaje_sin_coincidencias(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-personaje?q=zzz")
        assert "Sin coincidencias" in r.text

    def test_buscar_saga_sin_coincidencias(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/buscar-saga?q=zzz")
        assert "Sin coincidencias" in r.text
