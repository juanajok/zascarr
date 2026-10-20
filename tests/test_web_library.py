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

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Publisher, Series


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

    def test_la_tarjeta_dice_la_tradicion_como_el_filtro(self):
        """Caso real (2026-10-20): la tarjeta decía «franco_belgian»; el filtro, «Franco-belga»."""
        series = make_series("Thorgal")
        series.tradition = ComicTradition.FRANCO_BELGIAN
        session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        tarjeta = r.text[r.text.index('class="library-card-meta"'):]
        tarjeta = tarjeta[:tarjeta.index("</div>")]
        assert "Franco-belga (BD)" in tarjeta and "franco_belgian" not in tarjeta

    def test_los_buscadores_vacios_no_pintan_su_borde(self):
        """El desplegable vacío con borde dejaba una barra negra bajo «Buscar personaje / saga»."""
        from zascarr.main import STATIC_DIR
        css = (STATIC_DIR / "web.css").read_text(encoding="utf-8")
        assert ".filter-search-box .series-results:empty { display: none; }" in css

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

    def test_titulo_con_script_se_escapa(self):
        """XSS: un título con <script> debe renderizarse escapado por Jinja2,
        nunca como HTML ejecutable."""
        series = make_series('<script>alert(1)</script>')
        session = FakeSession([
            FakeExecResult([]),        # list_publishers_with_series
            FakeExecResult(1),         # count
            FakeExecResult([series]),  # items
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca")
        assert r.status_code == 200
        assert "&lt;script&gt;" in r.text
        assert "<script>alert(1)</script>" not in r.text


class TestResultados:

    def test_fragmento_con_filtro_de_tradicion(self):
        series = make_series("Thorgal")
        session = FakeSession([FakeExecResult(1), FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.get("/ui/biblioteca/resultados?tradition=franco_belgian")
        assert r.status_code == 200
        assert "Thorgal" in r.text
        # Es un fragmento: no repite el layout completo (topnav).
        assert "ZascArr" not in r.text

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
