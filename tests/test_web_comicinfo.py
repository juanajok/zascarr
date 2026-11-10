# ruff: noqa: E501
"""#448 BL-INF2 web: resumen previo y ejecución explícita de ComicInfo."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.comicinfo import ResumenAccionComicInfo
from zascarr.web import library as web


class _FakeSession:
    async def execute(self, _s):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: ["/a.cbz", "/b.cbr"]))

    async def commit(self):
        return None


def _override():
    async def _db():
        yield _FakeSession()
    app.dependency_overrides[get_db] = _db


def test_resumen_previo_muestra_cbz_y_cbr(monkeypatch):
    _override()
    try:
        r = TestClient(app).get("/ui/biblioteca/comicinfo")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "1 archivo vinculado" in r.text and "1 CBR" in r.text
    assert "no se ejecuta sola" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_ejecucion_explicita_muestra_recuentos(monkeypatch):
    _override()
    resultado = ResumenAccionComicInfo(total=2, cbr=1, aplicados=1, omitidos=1, ilegibles=0)
    monkeypatch.setattr(web, "leer_archivos_vinculados", AsyncMock(return_value=resultado))
    try:
        r = TestClient(app).post("/ui/biblioteca/comicinfo")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Datos aplicados" in r.text and ">1<" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_biblioteca_enlaza_la_accion_explicita():
    from tests.test_web_library import FakeExecResult, FakeSession, make_series, use_fake_session
    with use_fake_session(FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([make_series()])])) as client:
        r = client.get("/ui/biblioteca")
    assert "/ui/biblioteca/comicinfo" in r.text
