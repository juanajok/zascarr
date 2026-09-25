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

from datetime import datetime, timezone
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


class TestBotonAdoptar:

    def test_no_aparece_si_no_hay_nada_que_adoptar(self):
        # should_run() -> get_flag devuelve fila sin marcador, luego
        # count(series) > 0 -> no corre.
        session = FakeSession([
            FakeExecResult(informe_falso()),
            FakeExecResult(type("Fila", (), {"values": {}})()),
            FakeExecResult(7),  # ya hay 7 series: catálogo no vacío
        ])
        with use_fake_session(session) as client:
            r = client.get("/ui/auditoria")
        assert "Adoptar mi biblioteca" not in r.text

    def test_adoptar_sobre_biblioteca_ya_adoptada_no_hace_nada(self):
        session = FakeSession([
            FakeExecResult(type("Fila", (), {"values": {"_library_adoption_done": True}})()),
        ])
        with use_fake_session(session) as client:
            r = client.post("/ui/auditoria/adoptar")
        assert r.status_code == 200
        assert "ya estaba adoptada" in r.text
