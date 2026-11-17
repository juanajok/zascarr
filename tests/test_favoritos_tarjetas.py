"""#1035: favorito en tarjetas y ficha."""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app


class _Db:
    def __init__(self, serie):
        self.serie = serie

    async def get(self, _modelo, _id):
        return self.serie

    async def flush(self):
        return None

    async def commit(self):
        return None


def _cliente(favorite=False):
    serie = SimpleNamespace(id=uuid4(), favorite=favorite)
    async def _db():
        yield _Db(serie)
    app.dependency_overrides[get_db] = _db
    return TestClient(app), serie


def test_hx_devuelve_fragmento_y_alterna():
    cliente, serie = _cliente()
    try:
        r = cliente.post(f"/ui/series/{serie.id}/favorito",
                         headers={"HX-Request": "true"})
        assert r.status_code == 200
        assert 'aria-pressed="true"' in r.text and "<svg" in r.text
        assert "Quitar de favoritas" in r.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_sin_hx_sigue_redirigiendo():
    cliente, serie = _cliente()
    try:
        r = cliente.post(f"/ui/series/{serie.id}/favorito", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/ui/series/")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_tarjeta_y_ficha_incluyen_boton():
    from pathlib import Path
    rejilla = Path("src/zascarr/web/templates/_rejilla_biblioteca.html").read_text()
    ficha = Path("src/zascarr/web/templates/series_detail.html").read_text()
    frag = Path("src/zascarr/web/templates/_favorito_boton.html").read_text()
    assert 'include "_favorito_boton.html"' in rejilla and "library-card-wrap" in rejilla
    assert 'include "_favorito_boton.html"' in ficha
    assert "hx-post" in frag and "aria-pressed" in frag and "favorito-btn" in frag
