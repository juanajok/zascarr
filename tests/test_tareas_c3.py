"""#991 C3: conversión no bloquea y estado."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services import tareas
from zascarr.web import series as web


class _Sesion:
    def __init__(self, serie):
        self._serie = serie

    async def get(self, _modelo, _id):
        return self._serie


def _serie():
    return SimpleNamespace(id=uuid4(), title="Thorgal", metadata_={}, metadata_source="v",
                           total_issues=1, tradition=None, publisher=None)


class _Lento:
    def __init__(self):
        self.resultado = SimpleNamespace(nombre_nuevo="x.cbz", metodo="recomprimir",
                                         tamano_salida=1, motivo=None, mensaje="ok",
                                         deshacer_token=None, file_id=str(uuid4()))

    async def confirmar(self, *_a, **_k):
        await asyncio.sleep(2.0)
        return self.resultado


def test_conversion_individual_no_bloquea_y_estado(monkeypatch):
    serie = _serie()
    servicio = _Lento()
    monkeypatch.setattr(web, "_servicio_conversion", lambda _db: servicio)

    async def _db():
        yield _Sesion(serie)

    app.dependency_overrides[get_db] = _db
    tareas._reset_para_pruebas()
    try:
        c = TestClient(app)
        inicio = time.monotonic()
        r = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir",
                   data={"token": "x"}, headers={"HX-Request": "true"})
        duracion = time.monotonic() - inicio
        assert r.status_code == 200 and duracion < 1.0
        assert "Conversión en curso" in r.text
        time.sleep(0.5)
        assert web._CONVERSIONES and all(
            d.get("resultado") is None for d in web._CONVERSIONES.values())
        time.sleep(2.1)
        tid = web._CONVERSIONES_ACTIVAS.get(f"individual:{serie.id}:x")
        # el endpoint de estado se prueba con el tid real de la tarea
        tid = next(iter(web._CONVERSIONES))
        estado = c.get(f"/ui/series/{serie.id}/conversion/estado/{tid}")
        assert estado.status_code == 200 and "conversion-resultado" in estado.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        tareas._reset_para_pruebas()
        web._CONVERSIONES.clear()
        web._CONVERSIONES_ACTIVAS.clear()
        web._CONVERSIONES_FIN.clear()


def test_lote_no_bloquea_y_duplicado(monkeypatch):
    serie = _serie()
    clase = SimpleNamespace(archivos=[1, 2])

    class _S:
        async def previsualizar_lote(self, _sid):
            return clase

    _S.__name__ = "ConversionDeArchivo"

    monkeypatch.setattr(web, "_servicio_conversion", lambda _db: _S())

    async def _db():
        yield _Sesion(serie)

    app.dependency_overrides[get_db] = _db
    tareas._reset_para_pruebas()
    monkeypatch.setattr(web, "_fondo_lote", lambda *a, **k: asyncio.sleep(2.0))
    try:
        c = TestClient(app)
        inicio = time.monotonic()
        r = c.post(f"/ui/series/{serie.id}/convertir",
                   headers={"HX-Request": "true"})
        assert r.status_code == 200 and time.monotonic() - inicio < 1.0
        assert "Conversión en curso" in r.text
        r2 = c.post(f"/ui/series/{serie.id}/convertir",
                    headers={"HX-Request": "true"})
        assert r2.status_code == 200 and "Conversión en curso" in r2.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        tareas._reset_para_pruebas()
        web._CONVERSIONES.clear()
        web._CONVERSIONES_ACTIVAS.clear()
        web._CONVERSIONES_FIN.clear()


def test_estado_no_expone_conversion_de_otra_serie(monkeypatch):
    serie_a = _serie()
    serie_b = _serie()
    web._CONVERSIONES["tid-x"] = {"tipo": "individual", "series": serie_a,
                                  "file_id": uuid4(), "resultado": None, "error": None}
    async def _db():
        yield SimpleNamespace(get=lambda *a: None)
    # Endpoint no usa la BD para el chequeo de propiedad; basta con la sesión.
    app.dependency_overrides[get_db] = _db
    try:
        c = TestClient(app)
        r = c.get(f"/ui/series/{serie_b.id}/conversion/estado/tid-x")
        assert r.status_code == 404
    finally:
        app.dependency_overrides.pop(get_db, None)
        web._CONVERSIONES.clear()


def test_poda_de_conversiones():
    serie = _serie()
    web._CONVERSIONES.clear()
    web._CONVERSIONES_FIN.clear()
    for i in range(25):
        web._CONVERSIONES[f"t{i}"] = {"tipo": "individual", "series": serie}
    web._podar_conversiones()
    assert len(web._CONVERSIONES) <= 20


def test_error_obj_en_fondo_confirmar(monkeypatch):

    class TokenCaducadoError(Exception):
        pass

    class _SesionCtx:
        async def __aenter__(self):
            return SimpleNamespace()

        async def __aexit__(self, *a):
            return False

    class _Servicio:
        def __init__(self, *_a, **_k):
            pass

        async def confirmar(self, *_a, **_k):
            raise TokenCaducadoError("caducado")

    web._CONVERSIONES.clear()
    web._CONVERSIONES["tid-err"] = {"tipo": "individual", "series": _serie(),
                                    "file_id": uuid4(), "resultado": None, "error": None}
    monkeypatch.setattr(web.database, "async_session_factory", lambda: _SesionCtx())
    monkeypatch.setattr(web, "ConversionDeArchivo", _Servicio)
    asyncio.run(web._fondo_confirmar("tid-err", "tok", uuid4(), uuid4(), False))
    assert web._CONVERSIONES["tid-err"]["error"] == "TokenCaducadoError"
    assert isinstance(web._CONVERSIONES["tid-err"]["error_obj"], TokenCaducadoError)
    web._CONVERSIONES.clear()


def test_deshacer_no_bloquea(monkeypatch):
    serie = _serie()

    async def _db():
        yield _Sesion(serie)

    app.dependency_overrides[get_db] = _db
    tareas._reset_para_pruebas()

    async def _lento(*_a, **_k):
        await asyncio.sleep(2.0)

    monkeypatch.setattr(web, "_fondo_deshacer", _lento)
    try:
        c = TestClient(app)
        inicio = time.monotonic()
        r = c.post(f"/ui/series/{serie.id}/archivos/{uuid4()}/convertir/deshacer",
                   data={"token": "x"}, headers={"HX-Request": "true"})
        assert r.status_code == 200 and time.monotonic() - inicio < 1.0
        assert "Conversión en curso" in r.text
    finally:
        app.dependency_overrides.pop(get_db, None)
        tareas._reset_para_pruebas()
        web._CONVERSIONES.clear()
        web._CONVERSIONES_ACTIVAS.clear()
        web._CONVERSIONES_FIN.clear()


def test_paquete_crea_y_cierra_tarea(monkeypatch):
    from zascarr.models import PaqueteEstado
    from zascarr.web import auditoria

    class _Op:
        id = uuid4()
        estado = PaqueteEstado.VERIFICADO
        total_entradas = 2
        items = [{"nombre": "a.cbz"}, {"nombre": "b.cbz"}]

    class _SesionCtx:
        async def __aenter__(self):
            return SimpleNamespace(get=lambda *a, **k: _async_return(_Op()))

        async def __aexit__(self, *a):
            return False

    async def _publicar(*_a, **_k):
        return _Op()

    tareas._reset_para_pruebas()
    monkeypatch.setattr(auditoria.database, "async_session_factory", lambda: _SesionCtx())
    monkeypatch.setattr(auditoria, "publicar_e_importar", _publicar)
    asyncio.run(auditoria._procesar_paquete(str(uuid4())))
    recientes = tareas.snapshot(incluir_recientes=True, ahora=time.monotonic() + 1)["tareas"]
    assert recientes and recientes[-1]["tipo"] == "paquete"
    assert recientes[-1]["estado"] in {"terminada", "error"}


async def _async_return(valor):
    return valor
