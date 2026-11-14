"""BL-E5 (#164): búfer de logs recientes y descarga desde el dashboard."""
from __future__ import annotations

from fastapi.testclient import TestClient

from zascarr.main import app
from zascarr.utils import registro_reciente as rr


def setup_function() -> None:
    rr.limpiar()


def test_captura_redacta_credenciales_y_conserva_contexto():
    rr.capturar(None, "info", {
        "event": "fallo_de_prueba", "log_level": "error", "timestamp": "2026-11-14T17:00:00Z",
        "password": "NO-DEBE-SALIR", "api_key": "TAMPOCO",
        "mensaje": "token=SECRETO y https://usuario:clave@example.com/x?token=OTRO&ok=1",
    })
    texto = rr.texto_reciente()
    assert "fallo_de_prueba" in texto
    assert "NO-DEBE-SALIR" not in texto and "TAMPOCO" not in texto
    assert "SECRETO" not in texto and "OTRO" not in texto
    assert "usuario:clave" not in texto
    assert "example.com" in texto


def test_descarga_como_fichero_sin_cache():
    rr.capturar(None, "info", {"event": "zascarr.starting", "log_level": "info"})
    r = TestClient(app).get("/ui/logs")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert "attachment; filename=\"zascarr-logs-" in r.headers["content-disposition"]
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "zascarr.starting" in r.text


def test_sin_eventos_el_fichero_lo_explica():
    r = TestClient(app).get("/ui/logs")
    assert r.status_code == 200
    assert "No hay registros recientes" in r.text


def test_el_dashboard_ofrece_el_boton():
    from tests.test_web_dashboard import pagina, vista
    html = pagina(vista())
    assert 'href="/ui/logs"' in html and "Descargar logs" in html


def test_el_logger_real_pasa_por_el_buffer_y_redacta():
    import structlog
    rr.instalar_captura()
    rr.limpiar()
    structlog.get_logger("prueba").info("evento_real", token="NO-SALE", ruta="/media/x.cbz")
    texto = rr.texto_reciente()
    assert "evento_real" in texto and "/media/x.cbz" in texto
    assert "NO-SALE" not in texto
