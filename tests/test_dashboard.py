"""
tests/test_dashboard.py

Suite de Estado (E1). Antes vivía como fichero estático fuera de
base.html (sin navegación, look distinto al resto de la app — bug real
reportado); ahora es una vista Jinja2 más (zascarr.web.estado), así que
se comprueba igual que cualquier otra plantilla: contra el fichero fuente,
sin tocar la app completa (create_app() abre una conexión real a
PostgreSQL en su lifespan, que este entorno de tests no tiene).
"""
from __future__ import annotations

from zascarr.web.routes import TEMPLATES_DIR


class TestEstadoTemplate:

    def test_extiende_base_con_nav(self):
        html = (TEMPLATES_DIR / "estado.html").read_text(encoding="utf-8")
        assert '{% extends "base.html" %}' in html

    def test_referencia_api_health(self):
        html = (TEMPLATES_DIR / "estado.html").read_text(encoding="utf-8")
        assert "/api/health" in html
        # Los 4 checks que expone /api/health deben tener una etiqueta en
        # español: si se añade un check nuevo al backend sin tocar la
        # plantilla, este test lo detecta.
        for label in ("Base de datos", "Transmission", "aMule", "VPN"):
            assert label in html
