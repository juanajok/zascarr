"""
tests/test_web_series.py

Suite de la ficha de serie mínima (C2) — /ui/series/{id}. Solo lo que
pide C2: presentes/ausentes correctos, sin el bug de sort_order truncado
(ya cubierto a nivel de cálculo en test_api_series.py; aquí se prueba
que la página los renderiza).
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, Series


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return FakeScalarResult(self._rows)


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


def make_series(total_issues=None) -> Series:
    return Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN,
                  total_issues=total_issues, start_year=1977)


class TestFichaSerie:

    def test_serie_inexistente_da_404(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.get(f"/ui/series/{uuid4()}")
        assert r.status_code == 404

    def test_muestra_huecos_y_presentes(self):
        series = make_series(total_issues=3)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([1.0, 3.0]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "Thorgal" in r.text
        assert "#2" in r.text  # falta
        assert "#1" in r.text  # presente
        assert "#3" in r.text

    def test_regresion_annual_1_5_no_oculta_el_hueco_del_1(self):
        series = make_series(total_issues=2)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([1.5]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert "Te faltan" in r.text
        assert "#1" in r.text  # el 1.5 no lo cubre

    def test_sin_total_issues_no_calcula_huecos(self):
        series = make_series(total_issues=None)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{series.id}")
        assert r.status_code == 200
        assert "no se puede calcular huecos" in r.text
