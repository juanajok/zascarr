"""#418 (AC-33): sin `unar`, /api/health avisa (no es un error) y el arranque no falla."""
from __future__ import annotations

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.utils import lector_rar


def test_sin_el_lector_hay_un_aviso_y_no_cambia_el_estado(monkeypatch):
    from zascarr.api.health import AVISO_LECTOR_RAR

    class _Db:
        async def execute(self, _s):
            return None

    async def _get_db():
        yield _Db()

    app.dependency_overrides[get_db] = _get_db
    try:
        monkeypatch.setattr(lector_rar, "disponible", lambda: False)
        r = TestClient(app).get("/api/health")
        assert r.status_code == 200
        assert r.json()["warnings"]["lector_rar"] == AVISO_LECTOR_RAR
        monkeypatch.setattr(lector_rar, "disponible", lambda: True)
        assert "lector_rar" not in TestClient(app).get("/api/health").json()["warnings"]
    finally:
        app.dependency_overrides.pop(get_db, None)
