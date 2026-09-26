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

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, LegalAcknowledgment, Series, Wishlist, WishlistStatus
from zascarr.services.orchestrator import Orchestrator
from zascarr.services.prowlarr import SearchResult


def _accepted() -> "FakeExecResult":
    """Fila de la comprobación de aviso legal (gate de rutas de riesgo)
    — va SIEMPRE la primera en la cola de las rutas gateadas, antes que
    cualquier query propia del endpoint."""
    return FakeExecResult([LegalAcknowledgment(legal_version="x")])


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

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


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
        # Segunda query de la ruta (D9): is_acknowledged, tras la de items.
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([item]), _accepted()])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Sandman" in r.text
        assert "Aviso legal pendiente" not in r.text

    def test_pagina_vacia_muestra_mensaje(self):
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([]), _accepted()])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Nada en la lista de deseos" in r.text

    def test_aviso_legal_pendiente_muestra_banner(self):
        """D9: el aviso legal pendiente es un banner global de la página,
        no un last_error inventado por fila (ver services/orchestrator.py)."""
        with use_fake_session(FakeSession(exec_queue=[FakeExecResult([]), FakeExecResult([])])) as client:
            r = client.get("/ui/wishlist")
        assert r.status_code == 200
        assert "Aviso legal pendiente" in r.text


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
        session = FakeSession(exec_queue=[_accepted(), FakeExecResult([item])])
        with use_fake_session(session) as client:
            r = client.post("/ui/wishlist/anadir", data={"series_id": str(series.id)})
        assert r.status_code == 200
        assert "Thorgal" in r.text
        assert len(session.added) == 1

    def test_sin_aceptar_el_aviso_legal_da_403_con_hx_redirect(self):
        session = FakeSession(exec_queue=[FakeExecResult([])])  # sin acknowledgment
        with use_fake_session(session) as client:
            r = client.post("/ui/wishlist/anadir", data={"series_id": str(uuid4())})
        assert r.status_code == 403
        assert r.headers["hx-redirect"] == "/ui/legal"


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
            exec_queue=[_accepted(), FakeExecResult([row_item])],
        )
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/reintentar")
        assert r.status_code == 200
        assert "Mortadelo" in r.text

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/reintentar")
        assert r.status_code == 404


class TestBuscarAhora:
    """D10: ver candidatos reales antes de enviar nada a descargar."""

    def test_muestra_los_candidatos_encontrados(self, monkeypatch):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        monkeypatch.setattr(
            Orchestrator, "preview_candidates",
            AsyncMock(return_value=[SearchResult(
                title="Batman #1.cbz", indexer="test", download_url="magnet:?xt=urn:btih:abc",
                size_bytes=52_428_800, seeders=12, category="comics",
            )]),
        )
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
        assert r.status_code == 200
        assert "Batman #1.cbz" in r.text
        assert "Descargar este" in r.text
        assert "CBZ" in r.text

    def test_sin_candidatos_muestra_el_motivo_de_d9(self, monkeypatch):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED,
                        last_error="No se encontró nada en las fuentes activas")
        monkeypatch.setattr(Orchestrator, "preview_candidates", AsyncMock(return_value=[]))
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
        assert r.status_code == 200
        assert "No se encontró nada en las fuentes activas" in r.text

    def test_sin_query_construible_da_mensaje_generico(self, monkeypatch):
        item = Wishlist(id=uuid4(), status=WishlistStatus.WANTED)
        monkeypatch.setattr(Orchestrator, "preview_candidates", AsyncMock(return_value=None))
        session = FakeSession(get_map={(Wishlist, item.id): item}, exec_queue=[_accepted()])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/buscar-ahora")
        assert r.status_code == 200
        assert "No se pudo construir la búsqueda" in r.text

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/buscar-ahora")
        assert r.status_code == 404

    def test_sin_aceptar_el_aviso_legal_da_403_con_hx_redirect(self):
        session = FakeSession(exec_queue=[FakeExecResult([])])  # sin acknowledgment
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/buscar-ahora")
        assert r.status_code == 403
        assert r.headers["hx-redirect"] == "/ui/legal"


class TestCancelarBusqueda:

    def test_devuelve_vacio_sin_tocar_la_bd(self):
        """Cancelar tras ver candidatos no deja nada a medias: ni
        siquiera hace falta tocar la sesión."""
        with use_fake_session(FakeSession()) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/cancelar-busqueda")
        assert r.status_code == 200
        assert r.text == ""


class TestEnviarCandidato:

    def _form(self, **overrides):
        data = {
            "title": "Batman #1.cbz", "indexer": "test",
            "download_url": "magnet:?xt=urn:btih:abc",
            "size_bytes": "52428800", "seeders": "12", "category": "comics",
        }
        data.update(overrides)
        return data

    def test_envia_el_candidato_elegido_y_devuelve_la_fila(self, monkeypatch):
        series = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
        item = Wishlist(id=uuid4(), series_id=series.id, status=WishlistStatus.WANTED)
        row_item = make_wishlist_item(series, status=WishlistStatus.DOWNLOADING)
        row_item.series = series
        row_item.issue = None
        enviado = AsyncMock(return_value=True)
        monkeypatch.setattr(Orchestrator, "send_manual_candidate", enviado)
        session = FakeSession(
            get_map={(Wishlist, item.id): item},
            exec_queue=[_accepted(), FakeExecResult([row_item])],
        )
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{item.id}/enviar-candidato", data=self._form())
        assert r.status_code == 200
        assert "Batman" in r.text
        enviado.assert_awaited_once()
        candidato_enviado = enviado.await_args.args[1]
        assert candidato_enviado.title == "Batman #1.cbz"
        assert candidato_enviado.download_url == "magnet:?xt=urn:btih:abc"

    def test_item_inexistente_da_404(self):
        with use_fake_session(FakeSession(exec_queue=[_accepted()])) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/enviar-candidato", data=self._form())
        assert r.status_code == 404

    def test_sin_aceptar_el_aviso_legal_da_403_con_hx_redirect(self):
        session = FakeSession(exec_queue=[FakeExecResult([])])  # sin acknowledgment
        with use_fake_session(session) as client:
            r = client.post(f"/ui/wishlist/{uuid4()}/enviar-candidato", data=self._form())
        assert r.status_code == 403
        assert r.headers["hx-redirect"] == "/ui/legal"
