"""
tests/test_legal.py

Suite del blindaje legal: aceptación del aviso y la dependencia que la
exige. Solo gatea rutas que disparan red/descarga (ver services/legal.py
y su docstring) — biblioteca/pendientes/ficha de serie no llevan esto.
"""
from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import LegalAcknowledgment
from zascarr.services.legal import (
    current_legal_version,
    get_acknowledgment,
    is_acknowledged,
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


class TestTextoDelAviso:
    """Caso real (2026-10-20): el aviso enseñaba «[web:168]» y listas como párrafos con guiones.
    Se limpió el propio LEGAL.md (no al pintarlo): cambia `legal_version` y hay que volver a
    aceptarlo."""

    def test_el_fichero_no_lleva_marcas_de_cita(self):
        from zascarr.services.legal import LEGAL_MD_PATH, render_legal_html
        assert "[web:" not in LEGAL_MD_PATH.read_text(encoding="utf-8")
        assert "[web:" not in render_legal_html()

    def test_cada_lista_va_separada_de_su_frase_y_sale_como_lista(self):
        """Python-Markdown exige una línea en blanco antes de una lista."""
        import re

        from zascarr.services.legal import LEGAL_MD_PATH, render_legal_html
        crudo = LEGAL_MD_PATH.read_text(encoding="utf-8")
        assert not re.search(r"^(?![ \t]*[-*] |[ \t]*\|)[^\n]*\S[^\n]*\n[-*] ", crudo, re.M)
        assert "<p>Esto significa que:</p>\n<ul>" in render_legal_html()

    def test_la_version_es_el_hash_del_fichero(self):
        """Lo que se acepta es el fichero: cambiarlo obliga a aceptar de nuevo."""
        import hashlib

        from zascarr.services.legal import LEGAL_MD_PATH, current_legal_version
        crudo = LEGAL_MD_PATH.read_text(encoding="utf-8")
        assert current_legal_version() == hashlib.sha256(crudo.encode("utf-8")).hexdigest()[:16]


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
                                  accepted_at=datetime.now(UTC))
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
            await require_legal_acknowledgment(request=_request(), db=session)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "legal_acknowledgment_required"
        assert exc_info.value.headers["HX-Redirect"] == "/ui/legal?volver=%2Fui%2Fdeseados"

    @pytest.mark.asyncio
    async def test_no_lanza_si_aceptado(self):
        ack = LegalAcknowledgment(legal_version=current_legal_version())
        session = FakeSession(rows=[ack])
        await require_legal_acknowledgment(request=_request(), db=session)  # no debe lanzar


def _request(path="/ui/deseados", query=""):
    return Request({"type": "http", "method": "GET", "path": path,
                    "query_string": query.encode(), "headers": []})


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
                                  accepted_at=datetime.now(UTC))
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
                                  accepted_at=datetime.now(UTC))
        with use_fake_session(FakeSession(rows=[ack])) as client:
            r = client.get("/ui/legal")
        assert "aceptado" in r.text.lower()

    def test_accept_sin_las_tres_casillas_no_registra(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post("/ui/legal/accept", data={"acepto_1": "true"}, follow_redirects=False)
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/legal?volver=%2Fui%2Fbiblioteca&falta=1"
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


class TestUatp01RetornoDelAviso:
    def test_aceptar_desde_deseados_vuelve_al_contexto(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true",
                      "volver": "/ui/deseados?q=flash&vista=lista"},
                follow_redirects=False,
            )
        assert r.status_code == 303
        assert r.headers["location"] == "/ui/deseados?q=flash&vista=lista"
        assert len(session.added) == 1

    @pytest.mark.parametrize("destino", [
        "https://evil.example/x",
        "//evil.example/x",
        "/ui/legal",
        "/ui/../api/health",
        "/api/health",
    ])
    def test_destino_invalido_cae_al_respaldo_local(self, destino):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "acepto_2": "true", "acepto_3": "true",
                      "volver": destino},
                follow_redirects=False,
            )
        assert r.headers["location"] == "/ui/biblioteca"

    def test_falta_conserva_el_destino_y_lo_explica(self):
        session = FakeSession()
        with use_fake_session(session) as client:
            r = client.post(
                "/ui/legal/accept",
                data={"acepto_1": "true", "volver": "/ui/deseados?q=flash"},
                follow_redirects=False,
            )
        assert r.headers["location"] == (
            "/ui/legal?volver=%2Fui%2Fdeseados%3Fq%3Dflash&falta=1")
        assert session.added == []

    def test_wizard_conserva_destino_en_el_formulario(self):
        with use_fake_session(FakeSession(rows=[])) as client:
            r = client.get("/ui/legal?volver=%2Fui%2Fdeseados%3Fq%3Dflash")
        assert 'name="volver" value="/ui/deseados?q=flash"' in r.text

    @pytest.mark.asyncio
    async def test_el_gate_conserva_la_pagina_htmx(self):
        session = FakeSession(rows=[])
        request = Request({
            "type": "http", "method": "POST", "path": "/ui/wishlist/anadir",
            "query_string": b"", "headers": [(b"hx-current-url", b"http://localhost/ui/deseados?q=flash")],
        })
        with pytest.raises(HTTPException) as exc:
            await require_legal_acknowledgment(request=request, db=session)
        assert exc.value.headers["HX-Redirect"] == "/ui/legal?volver=%2Fui%2Fdeseados%3Fq%3Dflash"
