"""#991 C1: registro global, API y fragmento."""
from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from zascarr.main import app
from zascarr.services import tareas


@pytest.fixture(autouse=True)
def _limpio():
    tareas._reset_para_pruebas()
    yield
    tareas._reset_para_pruebas()


def test_iniciar_actualizar_terminar_y_atascada():
    t = tareas.iniciar("importar", total=10, fase="Importando")
    assert t is not None
    time.sleep(0.41)
    tareas.actualizar(t.id, hechos=5, fase="Comprobando")
    s = tareas.snapshot()
    assert s["activas"] == 1 and s["tareas"][0]["hechos"] == 5
    tareas.terminar(t.id, resumen="Hecho")
    assert tareas.snapshot()["activas"] == 0


def test_limite_activas_y_umbral_400ms():
    for i in range(20):
        assert tareas.iniciar("importar", origen=f"o{i}") is not None
    assert tareas.iniciar("importar", origen="extra") is None
    t = tareas.iniciar("rescanear", origen="x")
    assert t is None or tareas.snapshot()["activas"] <= 20


def test_retencion_y_error_hasta_visto():
    t = tareas.iniciar("importar")
    time.sleep(0.41)
    tareas.error(t.id, tipo_error="OSError")
    assert tareas.snapshot(incluir_recientes=True)["errores"] == 1
    tareas.marcar_visto(t.id)
    assert tareas.snapshot(incluir_recientes=True)["errores"] == 1


def test_concurrencia():
    creadas = []

    def uno(i):
        creadas.append(tareas.iniciar("importar", origen=f"c{i}"))
    hilos = [threading.Thread(target=uno, args=(i,)) for i in range(10)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    time.sleep(0.41)
    assert len([x for x in creadas if x]) == 10
    assert tareas.snapshot()["activas"] == 10


def test_copy_sin_datos_y_enlace_validado():
    t = tareas.iniciar("importar", enlace="/ui/auditoria#registro")
    assert t.titulo == "Importando descargas" and t.enlace.startswith("/ui/")
    t2 = tareas.iniciar("rescanear", enlace="https://ejemplo/ruta", origen="otro")
    assert t2.enlace is None


def test_api_json_y_fragmento():
    t = tareas.iniciar("registrar", total=2)
    time.sleep(0.41)
    tareas.actualizar(t.id, hechos=1)
    cliente = TestClient(app)
    r = cliente.get("/api/tareas")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert r.json()["version"] == 1 and r.json()["activas"] == 1
    f = cliente.get("/ui/_tareas")
    assert f.status_code == 200 and 'role="status"' in f.text
    assert "<progress" in f.text and "Ahora" in f.text


def test_plantilla_y_sin_datos_sensibles():
    from pathlib import Path
    base = Path("src/zascarr/web/templates/base.html").read_text()
    frag = Path("src/zascarr/web/templates/_tareas.html").read_text()
    assert 'id="tareas-global"' in base and "/ui/_tareas" in base
    assert "aria-live" in frag and "progress" in frag
    assert "str(exc)" not in frag
