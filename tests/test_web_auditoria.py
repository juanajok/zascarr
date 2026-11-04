"""
tests/test_web_auditoria.py

Contrato HTTP de /ui/auditoria (B16). Mismo patrón que test_pendientes.py:
get_db sobrescrito con una sesión falsa, sin Postgres.

Lo que se protege aquí es el ORDEN de la historia: la pantalla informa
primero y solo ofrece adoptar después. Que el botón de adoptar no
aparezca cuando no toca no es cosmético — es la diferencia entre "el
sistema informa y decide la persona" y lo que hacía antes.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app


class FakeExecResult:
    def __init__(self, value=None):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalar(self):
        return self._value


class FakeSession:
    def __init__(self, exec_queue=None):
        self._exec_queue = list(exec_queue or [])
        self.added: list = []
        self.flush = AsyncMock()

    async def execute(self, _statement):
        return self._exec_queue.pop(0) if self._exec_queue else FakeExecResult(None)

    def add(self, obj):
        self.added.append(obj)


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            async def _get_db():
                yield session
            app.dependency_overrides[get_db] = _get_db
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def informe_falso(**extra):
    base = {
        "kind": "audit", "files_hashed": 4, "bytes_hashed": 100,
        "bytes_recuperables": 2147483648, "truncado": False,
        "mismo_contenido": [], "misma_obra": [],
        "carpetas_repetidas": [], "carpetas_vacias": [],
    }
    base.update(extra)

    class Run:
        details = base
        started_at = datetime(2026, 9, 25, tzinfo=timezone.utc)
        files_scanned = 42
    return Run()


class TestIndex:

    def test_sin_informe_previo_invita_a_revisar(self):
        # 1ª query: último informe (ninguno). 2ª: should_run -> get_flag.
        session = FakeSession([FakeExecResult(None)])
        with use_fake_session(session) as client:
            r = client.get("/ui/auditoria")
        assert r.status_code == 200
        assert "Revisar mi biblioteca" in r.text

    def test_dice_que_no_toca_nada_del_disco(self):
        """La garantía de B16 tiene que estar delante del coleccionista,
        no solo en el código."""
        with use_fake_session(FakeSession([FakeExecResult(None)])) as client:
            r = client.get("/ui/auditoria")
        assert "no borra" in r.text and "no mueve" in r.text

    def test_carpetas_repetidas_se_muestran_con_las_dos_rutas(self):
        informe = informe_falso(carpetas_repetidas=[
            {"ruta_a": "/lib/Comics/Superman (1987)",
             "ruta_b": "/lib/Comics/Superman Vol2 (Ed.Zinco)",
             "comunes": 140, "solo_en_a": 0, "solo_en_b": 0},
        ])
        with use_fake_session(FakeSession([FakeExecResult(informe)])) as client:
            r = client.get("/ui/auditoria")
        assert "Superman (1987)" in r.text
        assert "Superman Vol2 (Ed.Zinco)" in r.text
        assert "140" in r.text
        assert "Son exactamente iguales" in r.text

    def test_misma_obra_avisa_de_que_puede_ser_deliberado(self):
        """No es un duplicado a borrar: el coleccionista puede querer
        las dos ediciones. Si el texto sugiere lo contrario, empuja a
        borrar algo que quería conservar."""
        informe = informe_falso(misma_obra=[
            {"obra": "gideon falls #1", "rutas": ["/a/x.cbr", "/b/y.cbr"]},
        ])
        with use_fake_session(FakeSession([FakeExecResult(informe)])) as client:
            r = client.get("/ui/auditoria")
        assert "los quieras los dos" in r.text

    def test_biblioteca_limpia_lo_dice(self):
        with use_fake_session(FakeSession([FakeExecResult(informe_falso())])) as client:
            r = client.get("/ui/auditoria")
        assert "está limpia" in r.text


class TestRegistroEnLaPagina:
    """El registro ya no se decide al pintar la página: se pide aparte (así el recorrido del disco
    no la retrasa) y se ofrece AUNQUE haya catálogo previo. Los flujos reales están en
    `tests/test_registro_biblioteca_pg.py` (Postgres y ficheros reales)."""

    def test_la_pagina_pide_el_registro_aparte_y_no_trae_el_boton_antiguo(self):
        with use_fake_session(FakeSession([FakeExecResult(informe_falso())])) as client:
            r = client.get("/ui/auditoria")
        assert 'hx-get="/ui/auditoria/registro"' in r.text and 'hx-trigger="load"' in r.text
        assert "Adoptar mi biblioteca" not in r.text

    def test_adoptar_sobre_biblioteca_ya_registrada_no_lanza_nada(self):
        from zascarr.services import registro_biblioteca
        registro_biblioteca.reiniciar_para_pruebas()
        marcada = type("Fila", (), {"values": {"_library_adoption_done": True}})()
        # `puede_registrar` + `evaluar` (valores crudos, último informe) + `estado` del fragmento.
        session = FakeSession([FakeExecResult(marcada), FakeExecResult({"_library_adoption_done": True}),
                               FakeExecResult(None), FakeExecResult(marcada)])
        with use_fake_session(session) as client:
            r = client.post("/ui/auditoria/adoptar")
        assert r.status_code == 200
        assert "ya está registrada" in r.text
        assert not registro_biblioteca.estado_actual().en_marcha


class TestCabeceraDeNoReconocidos:
    """UX (2026-10-23): la garantía va una vez en la cabecera y habla de la lista; el único camino verificado para arreglar un fichero es la carpeta de
    descargas (`tests/test_importer_recorrido_de_descargas_pg.py`), y la frase habla de la COPIA para no contradecir «no mueve ninguno»."""

    def test_la_cabecera_dice_la_garantia_una_vez_y_el_camino_verificado(self):
        from pathlib import Path
        t = (Path(__file__).resolve().parents[1] / "src/zascarr/web/templates/_auditoria_informe.html").read_text(encoding="utf-8")
        t = " ".join(t.split())
        assert "No cambia, mueve ni borra ninguno de esta lista." in t
        assert ("Si arreglas una copia (por ejemplo, la descomprimes o pones .cbz al final de su nombre) y la dejas en tu carpeta de descargas, "
                "ZascArr intentará importarla; el original seguirá aquí.") in t
        assert "hasta que los conviertas" not in t                       # la cabecera antigua, que decía que ninguno de estos archivos contaba


class TestRutasDelHost:
    """#294: «Duplicados» habla el idioma del disco de la persona, no el del contenedor.

    El invariante es a propósito global: se recorren TODOS los `.audit-path` del HTML, no uno por
    bloque. Cubre los seis puntos de hoy y caza cualquier bloque nuevo que se añada sin pasar por
    `ruta_visible`. Por eso el fixture monta las cinco secciones: con una sola, el invariante
    pasaría en vacío y daría una red que no es red.
    """

    HOST = "/media/WDElements/Tebeos"

    def _informe(self):
        return informe_falso(
            carpetas_repetidas=[{"ruta_a": "/media/library/Comics/Superman (1987)",
                                 "ruta_b": "/media/library/Comics/Superman Vol2",
                                 "comunes": 140, "solo_en_a": 0, "solo_en_b": 0}],
            mismo_contenido=[{"rutas": ["/media/library/Comics/A/x.cbr",
                                        "/media/library/Comics/B/x.cbr"],
                              "size_bytes": 1024, "sha256": "abc"}],
            misma_obra=[{"obra": "gideon falls #1", "rutas": ["/media/library/Comics/C/y.cbr"]}],
            carpetas_vacias=[{"ruta": "/media/library/Comics/Vacía", "subcarpetas": 0}],
            no_reconocidos=[{"ruta": "/media/library/Comics/raro.rar",
                             "motivo": "extensión no admitida"}],
        )

    def _rutas_pintadas(self, html):
        return re.findall(r'class="audit-path">([^<]*)<', html)

    def _con_host(self, monkeypatch, host):
        from zascarr.utils import ruta_visible as modulo
        monkeypatch.setattr(modulo, "get_settings",
                            lambda: SimpleNamespace(library_path="/media/library", host_library_dir=host))

    def test_la_ruta_que_se_ve_es_la_del_host_y_no_la_del_contenedor(self, monkeypatch):
        # Caso real (Pi, 2026-10-22): la pantalla decía /media/library/… y el disco de la persona es
        # /media/WDElements/Tebeos.
        self._con_host(monkeypatch, self.HOST)
        with use_fake_session(FakeSession([FakeExecResult(self._informe())])) as client:
            r = client.get("/ui/auditoria")
        rutas = self._rutas_pintadas(r.text)
        assert len(rutas) == 7, rutas           # 2 + 2 + 1 + 1 + 1: las cinco secciones del fixture
        assert all(x.startswith(self.HOST) for x in rutas), rutas
        assert "/media/library" not in r.text

    def test_sin_host_las_rutas_se_ven_como_estan_guardadas(self, monkeypatch):
        self._con_host(monkeypatch, "")
        with use_fake_session(FakeSession([FakeExecResult(self._informe())])) as client:
            r = client.get("/ui/auditoria")
        rutas = self._rutas_pintadas(r.text)
        assert rutas and all(x.startswith("/media/library") for x in rutas), rutas

    def test_una_ruta_fuera_de_la_biblioteca_no_se_toca(self, monkeypatch):
        self._con_host(monkeypatch, self.HOST)
        informe = informe_falso(no_reconocidos=[{"ruta": "/mnt/usb/suelto.rar",
                                                 "motivo": "extensión no admitida"}])
        with use_fake_session(FakeSession([FakeExecResult(informe)])) as client:
            r = client.get("/ui/auditoria")
        assert "/mnt/usb/suelto.rar" in r.text
        assert self.HOST + "/mnt/usb" not in r.text

    def test_el_fragmento_de_analizar_tambien_traduce(self, monkeypatch):
        # Segunda ruta de render: no basta con que la página traiga el filtro.
        from zascarr.web import auditoria as modulo_auditoria

        class _SinTocarElDisco:
            def __init__(self, _db): ...
            async def run(self): return None

        self._con_host(monkeypatch, self.HOST)
        monkeypatch.setattr(modulo_auditoria, "LibraryAudit", _SinTocarElDisco)
        informe = informe_falso(carpetas_vacias=[{"ruta": "/media/library/Comics/Vacía",
                                                  "subcarpetas": 0}])
        with use_fake_session(FakeSession([FakeExecResult(informe)])) as client:
            r = client.post("/ui/auditoria/analizar")
        assert r.status_code == 200
        assert self.HOST + "/Comics/Vacía" in r.text
        assert "/media/library" not in r.text
