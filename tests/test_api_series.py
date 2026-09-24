"""
tests/test_api_series.py

Suite de GET /api/series/{id}/missing (C2): antes truncaba sort_order con
int(), así que un Annual/especial con sort_order=1.5 "cubría" el hueco del
número 1 aunque ese número no existiera de verdad. El test de regresión
es justo ese caso — sin él, un futuro cambio podría reintroducir el bug
sin que nada lo detecte.
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

    def scalar(self):
        return self._rows


class FakeSession:
    """Cola de resultados: primero la serie, luego los sort_order."""

    def __init__(self, queue: list):
        self._queue = list(queue)
        self.added: list = []

    async def execute(self, _statement):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


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
    return Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN,
                  total_issues=total_issues)


class TestMissingIssues:

    def test_serie_inexistente_da_404(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.get(f"/api/series/{uuid4()}/missing")
        assert r.status_code == 404

    def test_sin_total_issues_devuelve_vacio(self):
        series = make_series(total_issues=None)
        with use_fake_session(FakeSession([FakeExecResult([series])])) as client:
            r = client.get(f"/api/series/{series.id}/missing")
        assert r.status_code == 200
        assert r.json() == []

    def test_huecos_simples_sin_decimales(self):
        series = make_series(total_issues=5)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([1.0, 2.0, 3.0]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/api/series/{series.id}/missing")
        assert r.json() == [4, 5]

    def test_regresion_annual_1_5_no_cubre_el_hueco_del_1(self):
        """El bug original: int(1.5) == 1, así que un Annual con
        sort_order=1.5 hacía creer que el issue 1 existía. No debe pasar."""
        series = make_series(total_issues=3)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([1.5, 2.0, 3.0]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/api/series/{series.id}/missing")
        assert r.json() == [1]

    def test_sin_ningun_issue_todo_es_hueco(self):
        series = make_series(total_issues=3)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/api/series/{series.id}/missing")
        assert r.json() == [1, 2, 3]

    def test_completa_no_tiene_huecos(self):
        series = make_series(total_issues=3)
        session = FakeSession([
            FakeExecResult([series]),
            FakeExecResult([1.0, 2.0, 3.0]),
        ])
        with use_fake_session(session) as client:
            r = client.get(f"/api/series/{series.id}/missing")
        assert r.json() == []


class TestNoExportMasivo:
    """Blindaje legal (recomendable, ya satisfecho): ningún listado
    devuelve más de 100 series de golpe — deja explícito lo que ya
    hace `Query(..., le=100)` en list_series, no una feature nueva."""

    def test_page_size_por_encima_de_100_se_rechaza(self):
        with use_fake_session(FakeSession([])) as client:
            r = client.get("/api/series?page_size=101")
        assert r.status_code == 422

    def test_page_size_100_se_acepta(self):
        session = FakeSession([FakeExecResult(0), FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get("/api/series?page_size=100")
        assert r.status_code == 200


class TestMassAssignmentSeries:
    """M1: POST/PATCH /api/series usan esquemas Pydantic con extra='forbid'.
    Un campo interno (id, metadata_source, locked_fields, *_id de proveedor,
    title_norm, timestamps…) debe rechazarse con 422, no inyectarse en el ORM."""

    FORBIDDEN = {
        "id": str(uuid4()),
        "metadata_source": "manual",
        "locked_fields": ["id"],
        "comic_vine_id": 1,
        "anilist_id": 2,
        "tebeosfera_slug": "thorgal",
        "title_norm": "batman",
        "enrichment_attempted_at": "2026-01-01T00:00:00Z",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }

    def test_post_rechaza_campos_internos(self):
        for campo, valor in self.FORBIDDEN.items():
            with use_fake_session(FakeSession([])) as client:
                r = client.post("/api/series", json={"title": "M1", campo: valor})
            assert r.status_code == 422, f"POST con '{campo}' debería dar 422, dio {r.status_code}"

    def test_post_acepta_campos_validos(self):
        with use_fake_session(FakeSession([])) as client:
            r = client.post(
                "/api/series",
                json={"title": "Batman", "tradition": "american", "start_year": 2011},
            )
        assert r.status_code == 201

    def test_patch_rechaza_campos_internos(self):
        for campo, valor in self.FORBIDDEN.items():
            with use_fake_session(FakeSession([])) as client:
                r = client.patch(f"/api/series/{uuid4()}", json={campo: valor})
            assert r.status_code == 422, f"PATCH con '{campo}' debería dar 422, dio {r.status_code}"

    def test_patch_acepta_campos_validos(self):
        series = make_series()
        session = FakeSession([FakeExecResult([series])])
        with use_fake_session(session) as client:
            r = client.patch(f"/api/series/{series.id}", json={"status": "completed"})
        assert r.status_code == 200
