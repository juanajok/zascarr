"""#991 C1: registro global, API y fragmento."""
from __future__ import annotations

import threading
import time
from pathlib import Path

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
    t._fin -= 9
    assert tareas.snapshot(incluir_recientes=True)["errores"] == 0


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
    cuerpo = r.json()
    assert cuerpo["version"] == 1 and cuerpo["resumen"]["en_curso"] == 1
    assert set(cuerpo) == {"version", "generado", "resumen", "tareas"}
    tarea = cuerpo["tareas"][0]
    assert {"detalle", "run_id", "visto", "unidad"} <= set(tarea)
    assert tarea["unidad"] == "archivos"
    f = cliente.get("/ui/_tareas")
    assert f.status_code == 200 and 'role="status"' in f.text
    assert "<progress" in f.text and "Ahora" in f.text


def test_plantilla_y_sin_datos_sensibles():
    from pathlib import Path
    base = Path("src/zascarr/web/templates/base.html").read_text()
    frag = Path("src/zascarr/web/templates/_tareas.html").read_text()
    assert 'id="tareas-global"' in base and "/ui/_tareas" in base
    assert 'aria-live="polite"' in base and "progress" in frag
    assert "str(exc)" not in frag


@pytest.mark.asyncio
async def test_import_error_no_deja_tarea_en_curso(monkeypatch):
    import time

    from zascarr.services import importer as modulo

    def rompe(*_a, **_k):
        raise RuntimeError("fallo simulado")
    monkeypatch.setattr(modulo, "listar_comics", rompe)
    enc = modulo.Importer(db=None)
    with pytest.raises(RuntimeError):
        await enc.scan_and_import(disparador="prueba")
    time.sleep(0.41)
    tareas_err = [x for x in tareas.snapshot(incluir_recientes=True)["tareas"]
                  if x["estado"] == "en_curso"]
    assert not tareas_err


def test_post_visto_y_oob_cadencia():
    t = tareas.iniciar("importar", total=2)
    time.sleep(0.41)
    tareas.actualizar(t.id, hechos=1)
    cliente = TestClient(app)
    f = cliente.get("/ui/_tareas")
    assert "every 2s" in f.text and "tareas-cadencia" in f.text
    tareas.error(t.id, tipo_error="OSError")
    r = cliente.post(f"/ui/_tareas/visto/{t.id}")
    assert r.status_code == 200
    assert tareas.snapshot(incluir_recientes=True)["errores"] == 1
    t._fin -= 9
    assert tareas.snapshot(incluir_recientes=True)["errores"] == 0


def test_api_no_consume_anuncio_ui():
    tareas._reset_para_pruebas()
    tareas.iniciar("importar", origen="a")
    time.sleep(0.41)
    assert tareas.snapshot(incluir_recientes=True)["anuncio"] is None
    assert tareas.snapshot(incluir_recientes=True, consumir_anuncio=True)["anuncio"]


@pytest.mark.asyncio
async def test_registro_ocupado_y_cancelado_cierran_tarea(monkeypatch):
    from contextlib import asynccontextmanager

    from zascarr.services import registro_biblioteca as rb

    class Fabrica:
        def __call__(self):
            return self

        async def __aenter__(self):
            return object()

        async def __aexit__(self, *a):
            return False

    @asynccontextmanager
    async def sin_libre(_sesion):
        yield False

    monkeypatch.setattr(rb, "_cerrojo_de_registro", sin_libre)
    rb._estado = rb.EstadoRegistro()
    tareas._reset_para_pruebas()
    await rb._ejecutar(Fabrica())
    time.sleep(0.41)
    assert any(x["estado"] == "error" for x in tareas.snapshot(incluir_recientes=True)["tareas"])


@pytest.mark.asyncio
async def test_descargas_multi_ciclo_y_error(monkeypatch):
    from types import SimpleNamespace

    from zascarr.services import orchestrator as orq_mod
    from zascarr.services.orchestrator import Orchestrator
    orq_mod._tarea_descargas = None

    class Res:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    class Db:
        def __init__(self, items=None, falla=False):
            self.items = items or []
            self.falla = falla

        async def execute(self, *_a, **_k):
            if self.falla:
                raise RuntimeError("fallo bd")
            return Res(self.items)

        async def flush(self):
            return None

    tareas._reset_para_pruebas()
    orq = Orchestrator.__new__(Orchestrator)
    orq.db = Db([SimpleNamespace(id="1", status="downloading")])
    async def no_hecho(_item):
        return False
    orq._is_fulfilled = no_hecho
    assert await orq.check_completions() == 0
    time.sleep(0.41)
    assert tareas.snapshot(incluir_recientes=True)["activas"] == 1
    orq.db = Db([])
    assert await orq.check_completions() == 0
    assert tareas.snapshot(incluir_recientes=True)["activas"] == 0
    orq.db = Db([], falla=True)
    with pytest.raises(RuntimeError):
        await orq.check_completions()


def test_oob_no_reemplaza_details_y_conserva_foco():
    base = Path("src/zascarr/web/templates/base.html").read_text()
    frag = Path("src/zascarr/web/templates/_tareas.html").read_text()
    assert 'id="tareas-detalles"' in base and "<details" not in frag
    for ident in ("tareas-lista", "tareas-contador", "tareas-anuncio", "tareas-cadencia"):
        assert f'id="{ident}"' in frag and "hx-swap-oob" in frag
    assert "every 2s" in frag and "every 10s" in frag


def test_css_chip_en_flujo_y_panel_bajo_el_chip():
    css = Path("src/zascarr/static/web.css").read_text()
    assert ".tareas-fuera { position: relative; display: flex;" in css
    assert ".tareas-panel { position: relative; right: auto; left: auto; top: auto;" in css
    assert ".side .tareas-panel" not in css
    # Sin hoja inferior fija: el chip no flota sobre tarjetas/contenido.
    assert "bottom: 72px" not in css


def test_visto_form_y_panel():
    t = tareas.iniciar("importar", origen="visto")
    time.sleep(0.41)
    tareas.error(t.id, tipo_error="OSError")
    cliente = TestClient(app)
    r = cliente.post("/ui/_tareas/visto", data={"tid": t.id})
    assert r.status_code == 200
    base = Path("src/zascarr/web/templates/base.html").read_text()
    assert 'hx-post="/ui/_tareas/visto"' in base
    t2 = tareas.iniciar("importar", origen="visto2")
    time.sleep(0.41)
    tareas.error(t2.id, tipo_error="OSError")
    assert cliente.post("/ui/_tareas/visto", data={"tid": "ultimo"}).status_code == 200


def test_visto_marca_todos_los_errores_y_trigger_solo_apertura():
    cliente = TestClient(app)
    ids = []
    for i in range(2):
        t = tareas.iniciar("importar", origen=f"v{i}")
        time.sleep(0.41)
        tareas.error(t.id, tipo_error="OSError")
        ids.append(t.id)
    r = cliente.post("/ui/_tareas/visto")
    assert r.status_code == 200
    datos = tareas.snapshot(incluir_recientes=True)["tareas"]
    assert all(x["visto"] for x in datos if x["id"] in ids)
    base = Path("src/zascarr/web/templates/base.html").read_text()
    assert 'hx-trigger="click[!this.parentElement.open]"' in base
    assert 'hx-trigger="toggle"' not in base


def test_copia_exito_y_fallo(monkeypatch):
    from zascarr.services import ops_host
    from zascarr.web import copias

    copias._tarea_copia = None
    tareas._reset_para_pruebas()
    estados = {"v": type("V", (), {"en_marcha": True, "estado": "en_marcha"})()}
    monkeypatch.setattr(ops_host, "resolver_estado", lambda _s: estados["v"])
    monkeypatch.setattr(ops_host, "leer_copias", lambda _s: [])
    cliente = TestClient(app)
    assert cliente.get("/ui/copias/estado").status_code == 200
    time.sleep(0.41)
    assert tareas.snapshot(incluir_recientes=True)["activas"] == 1
    estados["v"] = type("V", (), {"en_marcha": False, "estado": "hecha"})()
    assert cliente.get("/ui/copias/estado").status_code == 200
    assert tareas.snapshot(incluir_recientes=True)["activas"] == 0
    copias._tarea_copia = None
    tareas._reset_para_pruebas()
    estados["v"] = type("V", (), {"en_marcha": True, "estado": "en_marcha"})()
    assert cliente.get("/ui/copias/estado").status_code == 200
    time.sleep(0.41)
    estados["v"] = type("V", (), {"en_marcha": False, "estado": "fallo"})()
    cliente.get("/ui/copias/estado")
    assert any(x["estado"] == "error" for x in tareas.snapshot(incluir_recientes=True)["tareas"])


def test_indicador_en_flujo_y_carrusel_estable():
    """#991/#1021: el chip no se superpone al título y las tarjetas miden igual."""
    base = Path("src/zascarr/web/templates/base.html").read_text()
    css = Path("src/zascarr/static/web.css").read_text()
    assert base.index('<main class="content"') < base.index('class="tareas-fuera"')
    assert base.index('id="tareas-anuncio"') < base.index('<main class="content"')
    assert base.index('id="tareas-cadencia"') < base.index('<main class="content"')
    assert "left: 252px" not in css
    assert ".tareas-fuera { position: relative; display: flex; justify-content: flex-end;" in css
    assert ".tareas-panel { position: relative; right: auto; left: auto; top: auto;" in css
    assert ".tareas-fuera .tareas-panel { position: fixed;" not in css
    assert ".escaparate-lista > li { flex: 0 0 160px; width: 160px; max-width: 160px; }" in css
