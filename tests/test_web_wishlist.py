"""
tests/test_web_wishlist.py

Suite de los endpoints HTMX de la lista de deseos (D1). Mismo patrón que
test_pendientes.py: sobrescribe get_db con una sesión falsa, prueba el
CONTRATO HTTP (200/404/400, qué fragmento devuelve cada ruta), no la
lógica de negocio (ya cubierta en test_wishlist_service.py).
"""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from secuenciarr.database import get_db
from secuenciarr.main import app
from secuenciarr.models import ComicTradition, Series, Wishlist, WishlistStatus


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return FakeScalarResult(self._rows)

    def scalar_one(self):
        return self._rows[0]


class FakeSession:
    def __init__(self, get_map=None, exec_queue=None):
        self._get_map = get_map or {}
        self._exec_queue = list(exec_queue or [])
        self.flush = AsyncMock()
        self.added: list = []
        self.deleted: list = []

    async def get(self, model, id_):
        return self._get_map.get((model, id_))

    async def execute(self, _statement):
        return self._exec_queue.pop(0)

    def add(self, obj):
        self.added.append(obj)

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


def make_wishlist_item(series=None, status=WishlistStatus.WANTED) -> Wishlist:
    return Wishlist(id=uuid4(), series_id=series.id if series else None,
                    issue_id=None, status=status)


class TestIndex:

    def test_pagina_lista_items(self):
        series = Series(id=uuid4(), title="Sandman", tradition=ComicTradition.AMERICAN)
        item = make_wishlist_item(series)
        item.series = series
        item.issue = None
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item])])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Sandman" in r.text

    def test_pagina_vacia_muestra_mensaje(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Nada en la lista de deseos" in r.text


class TestBuscarSerie:

    def test_devuelve_resultados_como_fragmento(self):
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN, start_year=2011)
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([series])])) as client:
            r = client.get("/ui/wishlist/buscar-serie?q=bat")
        assert r.status_code == 200
        assert "Batman" in r.text

    def test_sin_coincidencias(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist/buscar-serie?q=zzz")
        assert "Sin coincidencias" in r.text


class TestAnadir:

    def test_anade_y_devuelve_la_fila(self):
        series = Series(id=uuid4(), title="Thorgal", tradition=ComicTradition.FRANCO_BELGIAN)
        item = make_wishlist_item(series)
        item.series = series
        item.issue = None
        session = FakeSession(exec_queue=[FakeExecResult([item])])
        with use_fake_session(session) as client:
            r = client.post("/ui/wishlist/anadir", data={"series_id": str(series.id)})
        assert r.status_code == 200
        assert "Thorgal" in r.text
        assert len(session.added) == 1


class TestQuitar:

    def test_quitar_devuelve_vacio(self):
        item = Wishlist(id=uuid4())
        session = FakeSession(get_map={(Wishlist, item.id): item})
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/quitar")
        assert r.status_code == 200
        assert r.text == ""
        assert session.deleted == [item]

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/quitar")
        assert r.status_code == 404


class TestReintentar:

    def test_reintentar_devuelve_la_fila_actualizada(self):
        series = Series(id=uuid4(), title="Mortadelo", tradition=ComicTradition.TEBEO)
        item = Wishlist(id=uuid4(), series_id=series.id, status=WishlistStatus.FAILED)
        row_item = make_wishlist_item(series, status=WishlistStatus.WANTED)
        row_item.series = series
        row_item.issue = None
        session = FakeSession(
            get_map={(Wishlist, item.id): item},
            exec_queue=[FakeExecResult([row_item])],
        )
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/reintentar")
        assert r.status_code == 200
        assert "Mortadelo" in r.text

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/reintentar")
        assert r.status_code == 404
