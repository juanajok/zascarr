"""
tests/test_api_wishlist.py

Suite de la API JSON de wishlist (`api/wishlist.py`). Objetivo principal:
confirmar que M1 (mass assignment, `Wishlist(**data)` sobre el body
crudo) queda cerrado — un campo no declarado en WishlistCreate/
WishlistUpdate se ignora en vez de colarse hasta el modelo.
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from secuenciarr.database import get_db
from secuenciarr.main import app
from secuenciarr.models import Wishlist, WishlistStatus


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, exec_result=None):
        self._exec_result = exec_result
        self.flush = AsyncMock()
        self.refresh = AsyncMock()
        self.added: list = []
        self.deleted: list = []

    async def execute(self, _statement):
        return self._exec_result

    def add(self, obj):
        self.added.append(obj)

    async def get(self, model, id_):
        return None

    async def delete(self, obj):
        self.deleted.append(obj)


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


class TestAddToWishlistM1:

    def test_campo_no_declarado_se_ignora(self):
        """Antes: Wishlist(**data) — un id/added_at/download_ref arbitrario
        en el body se habría colado directo al modelo. Ahora WishlistCreate
        solo declara series_id/issue_id/priority/notes."""
        session = FakeSession()
        forged_id = str(uuid4())
        with use_fake_session(session) as client:
            r = client.post("/api/wishlist", json={
                "series_id": str(uuid4()),
                "id": forged_id,
                "added_at": "2020-01-01T00:00:00Z",
                "download_ref": "inyectado",
                "status": "imported",
            })
        assert r.status_code == 201
        created = session.added[0]
        assert str(created.id) != forged_id  # el id lo genera el modelo, no el body
        assert created.download_ref is None
        assert created.status != WishlistStatus.IMPORTED  # "status" no está en WishlistCreate

    def test_sin_series_id_ni_issue_id_da_422(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post("/api/wishlist", json={})
        assert r.status_code == 422


class TestUpdateWishlistM1:

    def test_solo_campos_declarados_se_aplican(self):
        item = Wishlist(id=uuid4(), priority=5)
        session = FakeSession(exec_result=FakeScalarResult([item]))
        with use_fake_session(session) as client:
            r = client.patch(f"/api/wishlist/{item.id}", json={
                "priority": 1,
                "series_id": str(uuid4()),  # no está en WishlistUpdate: se ignora
            })
        assert r.status_code == 200
        assert item.priority == 1
        assert item.series_id is None  # no se coló

    def test_item_inexistente_da_404(self):
        session = FakeSession(exec_result=FakeScalarResult([]))
        with use_fake_session(session) as client:
            r = client.patch(f"/api/wishlist/{uuid4()}", json={"priority": 1})
        assert r.status_code == 404
