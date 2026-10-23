"""
tests/test_web_errores.py — página de error propia (`web/errores.py`, revisión visual 2026-10-20).

Caso real: abrir una serie que ya no existe enseñaba `{"detail":"Serie no encontrada"}` en crudo,
fuera de la app. Ahora quien navega ve una página con menú y una salida; la API y HTMX no cambian.
"""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from tests.test_web_series import FakeExecResult, FakeSession, use_fake_session
from zascarr.database import get_db
from zascarr.main import app
from zascarr.web import errores

NAVEGADOR = {"Accept": "text/html,application/xhtml+xml"}


class TestQuienNavega:

    def test_una_serie_que_no_existe_da_una_pagina_y_no_json(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.get(f"/ui/series/{uuid4()}", headers=NAVEGADOR)
        assert r.status_code == 404
        assert r.headers["content-type"].startswith("text/html")
        assert '{"detail"' not in r.text
        assert "<h1>No está aquí</h1>" in r.text
        assert "Serie no encontrada" in r.text                 # el motivo concreto, si es una frase
        assert '<a class="btn primary" href="/ui/">Ir al Inicio</a>' in r.text
        assert '<nav class="nav"' in r.text                    # dentro de la app, con su menú
        assert '<section class="pagina-error">' in r.text      # gancho de la trama y el rótulo

    def test_una_ruta_que_no_existe_tambien(self):
        r = TestClient(app).get("/ui/esto-no-existe", headers=NAVEGADOR)
        assert r.status_code == 404 and "<h1>No está aquí</h1>" in r.text
        assert "Not Found" not in r.text                       # la frase genérica en inglés, fuera

    def test_un_fallo_inesperado_da_la_pagina_de_500_con_salida_al_estado(self):
        class _Rota(FakeSession):
            async def execute(self, _stmt):
                raise RuntimeError("boom")

        async def _db():
            yield _Rota([])

        app.dependency_overrides[get_db] = _db
        try:
            r = TestClient(app, raise_server_exceptions=False).get("/ui/biblioteca",
                                                                   headers=NAVEGADOR)
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert r.status_code == 500
        assert "<h1>Algo ha fallado</h1>" in r.text and 'href="/estado">Ver el estado' in r.text
        assert "boom" not in r.text                            # nada interno en superficie


class TestLoQueNoCambia:

    def test_la_api_sigue_con_su_json(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.get(f"/api/series/{uuid4()}", headers=NAVEGADOR)
        assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")

    def test_htmx_conserva_su_respuesta(self):
        """La página entera acabaría dentro del fragmento que esperaba el `hx-target`."""
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.get(f"/ui/series/{uuid4()}", headers={**NAVEGADOR, "HX-Request": "true"})
        assert r.status_code == 404 and r.json() == {"detail": "Serie no encontrada"}

    def test_un_post_mantiene_su_contrato(self):
        with use_fake_session(FakeSession([FakeExecResult([])])) as client:
            r = client.post(f"/ui/series/{uuid4()}/politica", data={"wishlist_policy": "ninguno"},
                            headers=NAVEGADOR)
        assert r.headers["content-type"].startswith("application/json")


class TestPiezas:

    def test_un_codigo_interno_no_se_ensena_como_motivo(self):
        assert not errores._es_frase("legal_acknowledgment_required", 403)
        assert not errores._es_frase("Not Found", 404)
        assert not errores._es_frase({"codigo": "x"}, 409)
        assert errores._es_frase("Serie no encontrada", 404)

    def test_si_pintar_la_pagina_falla_cae_a_html_minimo(self, monkeypatch):
        def _rompe(*_a, **_k):
            raise RuntimeError("plantilla rota")
        monkeypatch.setattr(errores.templates, "TemplateResponse", _rompe)
        r = TestClient(app).get("/ui/esto-no-existe", headers=NAVEGADOR)
        assert r.status_code == 404
        assert "<h1>No está aquí</h1>" in r.text and 'href="/ui/"' in r.text
