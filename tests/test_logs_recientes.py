"""BL-E5 (#164): búfer de logs recientes y descarga desde Estado."""
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


def test_el_inicio_ya_no_ofrece_los_registros():
    from tests.test_web_dashboard import pagina, vista
    html = pagina(vista())
    assert 'href="/ui/logs"' not in html
    assert "Descargar logs" not in html and "últimos registros" not in html


def test_estado_ofrece_el_acceso_en_diagnostico():
    from pathlib import Path
    plantilla = Path(__file__).resolve().parents[1] / "src/zascarr/web/templates/estado.html"
    t = plantilla.read_text(encoding="utf-8")
    assert 'id="diagnostico"' in t and 'href="/ui/logs"' in t
    assert "Registro de la aplicación" in t
    assert "Descargar los últimos registros" in t
    assert "sin rutas, nombres, contraseñas ni tokens" in t


def test_el_logger_real_pasa_por_el_buffer_y_redacta():
    import structlog
    rr.instalar_captura()
    rr.limpiar()
    structlog.get_logger("prueba").info("evento_real", token="NO-SALE", ruta="/media/x.cbz")
    texto = rr.texto_reciente()
    assert "evento_real" in texto and "/media/x.cbz" not in texto
    assert "x.cbz" not in texto and "NO-SALE" not in texto


def test_la_descarga_no_lleva_rutas_de_biblioteca():
    """#369: el fichero /ui/logs tampoco expone rutas ni nombres de la biblioteca."""
    import structlog

    from zascarr.utils.saneado_logs import instalar_saneo_logs
    instalar_saneo_logs()
    rr.instalar_captura()
    rr.limpiar()
    structlog.get_logger("prueba.ruta").error(
        "fallo en /media/library/Serie/foo.cbz", ruta="/media/library/Serie/foo.cbz")
    r = TestClient(app).get("/ui/logs")
    assert r.status_code == 200
    assert "/media/library" not in r.text and "foo.cbz" not in r.text
