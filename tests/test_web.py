"""
tests/test_web.py

Suite del esqueleto de la UI web (ADR 0001): router /ui, layout base,
HTMX vendorizado. Usa TestClient SIN entrar como context manager: así no
dispara el lifespan de la app real, que exige una conexión a PostgreSQL
que este entorno de tests no tiene — confirmado empíricamente antes de
escribir estos tests, no solo supuesto.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from zascarr.main import app

client = TestClient(app)


class TestStaticAssets:

    def test_htmx_vendorizado_se_sirve_y_es_la_version_esperada(self):
        r = client.get("/static/vendor/htmx.min.js")
        assert r.status_code == 200
        assert 'this.version="4.0.0"' in r.text

    def test_css_de_la_ui_se_sirve(self):
        r = client.get("/static/web.css")
        assert r.status_code == 200

    def test_estado_e1_sigue_funcionando_tras_montar_static_y_ui(self):
        r = client.get("/estado")
        assert r.status_code == 200
        assert "ZascArr" in r.text

    def test_raiz_redirige_a_la_biblioteca(self):
        """Bug real (reportado): "/" mandaba a Estado en vez de a la
        biblioteca, sin forma de volver. Ahora "/" es solo un redirect."""
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 307
        assert r.headers["location"] == "/ui/"
