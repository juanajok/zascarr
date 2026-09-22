"""
tests/test_dashboard.py

Suite del dashboard de estado (E1). No usa TestClient contra la app
completa: create_app() registra un lifespan que abre una conexión real a
PostgreSQL, que este entorno de tests no tiene. dashboard() es una función
de módulo justamente para poder probarla aislada de eso.
"""
from __future__ import annotations

from fastapi.responses import FileResponse

from zascarr.main import STATIC_DIR, dashboard


class TestDashboardRoute:

    async def test_sirve_el_fichero_dashboard_html(self):
        response = await dashboard()
        assert isinstance(response, FileResponse)
        assert str(response.path) == str(STATIC_DIR / "dashboard.html")

    def test_el_fichero_existe_y_referencia_api_health(self):
        html = (STATIC_DIR / "dashboard.html").read_text(encoding="utf-8")
        assert "/api/health" in html
        # Los 4 checks que expone /api/health deben tener una etiqueta en
        # español: si se añade un check nuevo al backend sin tocar el
        # dashboard, este test lo detecta.
        for label in ("Base de datos", "Transmission", "aMule", "VPN"):
            assert label in html
