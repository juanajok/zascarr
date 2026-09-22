"""
tests/test_legal.py

Suite del blindaje legal: aceptación del aviso y la dependencia que la
exige. Solo gatea rutas que disparan red/descarga (ver services/legal.py
y su docstring) — biblioteca/pendientes/ficha de serie no llevan esto.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import LegalAcknowledgment
from zascarr.services.legal import (
    current_legal_version, get_acknowledgment, is_acknowledged,
    require_legal_acknowledgment,
)


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    def __init__(self, rows=None):
        self._rows = rows or []
        self.flush = AsyncMock()
        self.added: list = []

    async def execute(self, _statement):
        return FakeExecResult(self._rows)

    def add(self, obj):
        self.added.append(obj)


class TestVersion:

    def test_version_estable_entre_llamadas(self):
        assert current_legal_version() == current_legal_version()

    def test_version_no_esta_vacia(self):
        assert len(current_legal_version()) > 0


class TestAcknowledgment:

    @pytest.mark.asyncio
    async def test_no_aceptado_sin_filas(self):
        session = FakeSession(rows=[])
        assert await is_acknowledged(session) is False
        assert await get_acknowledgment(session) is None

    @pytest.mark.asyncio
    async def test_aceptado_con_fila_de_la_version_actual(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(timezone.utc))
        session = FakeSession(rows=[ack])
        assert await is_acknowledged(session) is True

    @pytest.mark.asyncio
    async def test_acknowledge_anade_una_fila_con_la_version_actual(self):
        from zascarr.services.legal import acknowledge
        session = FakeSession()
        ack = await acknowledge(session)
        assert ack.legal_version == current_legal_version()
        assert session.added == [ack]


class TestRequireLegalAcknowledgment:

    @pytest.mark.asyncio
    async def test_lanza_403_con_hx_redirect_si_no_aceptado(self):
        session = FakeSession(rows=[])
        with pytest.raises(HTTPException) as exc_info:
            await require_legal_acknowledgment(db=session)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "legal_acknowledgment_required"
        assert exc_info.value.headers["HX-Redirect"] == "/ui/legal"

    @pytest.mark.asyncio
    async def test_no_lanza_si_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version())
        session = FakeSession(rows=[ack])
        await require_legal_acknowledgment(db=session)  # no debe lanzar


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


class TestApiLegalStatus:

    def test_no_aceptado(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/api/legal/status")
        assert r.status_code == 200
        assert r.json()["accepted"] is False

    def test_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(timezone.utc))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/api/legal/status")
        assert r.json()["accepted"] is True


class TestApiLegalAccept:

    def test_sin_acknowledged_true_da_400(self):
        with use_fake_session(FakeSession()) as client:
            r = client.post("/api/legal/accept", json={"acknowledged": False})
        assert r.status_code == 400

    def test_con_acknowledged_true_registra(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post("/api/legal/accept", json={"acknowledged": True})
        assert r.status_code == 201
        assert len(session.added) == 1


class TestUiLegal:

    def test_wizard_muestra_formulario_si_no_aceptado(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/ui/legal")
        assert r.status_code == 200
        assert "Aceptar y continuar" in r.text

    def test_wizard_muestra_estado_si_ya_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version(),
                                  accepted_at=datetime.now(timezone.utc))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/ui/legal")
        assert "aceptado" in r.text.lower()

    def test_accept_sin_las_tres_casillas_no_registra(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post("/ui/legal/accept", data={"acepto_1": "true"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/legal"
        assert session.added == []

    def test_accept_con_las_tres_casillas_registra_y_redirige(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true"},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/biblioteca"
        assert len(session.added) == 1

    def test_legal_full_renderiza_markdown(self):
        with use_fake_session(FakeSession()) as client:
            r = client.get("/legal")
        assert r.status_code == 200
        assert "Aviso Legal" in r.text
        assert "<h1>" in r.text or "<h2>" in r.text
