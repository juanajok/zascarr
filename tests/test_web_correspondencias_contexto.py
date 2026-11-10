# ruff: noqa: E501
"""MIT-M7 131-b: rutas de correspondencias y propuestas (sin navegador)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import EstadoEvaluacion, EstadoRegla, OrigenRegla, TipoDestino, TipoRegistro
from zascarr.services.correspondencias_contexto import CorrespondenciaVista, ResultadoEvaluacion
from zascarr.web import correspondencias_contexto as web


def _corr(estado=EstadoRegla.ACTIVA, version=1, raiz="Comics/Carlos", tipo_reg=TipoRegistro.ARCHIVO):
    return CorrespondenciaVista(
        id=uuid4(), correspondencia_id=uuid4(), version=version, supersedes_id=None,
        declaracion_version_id=uuid4(), contexto_raiz=raiz, incluir_descendientes=False,
        tipo_de_registro=tipo_reg, destino_tipo=TipoDestino.SERIE, destino_id=uuid4(),
        origen=OrigenRegla.LOCAL, estado=estado, vigente_desde=datetime.now(UTC),
        vigente_hasta=None)


def _decl():
    return SimpleNamespace(id=uuid4(), contexto_raiz="Comics/Carlos", version=2,
                           incluir_descendientes=False, estado=EstadoRegla.ACTIVA,
                           tipo_de_significado=SimpleNamespace(value="publicacion"))


def _get_db():
    async def _db():
        yield SimpleNamespace()
    return _db


def _cliente(monkeypatch, **mocks):
    app.dependency_overrides[get_db] = _get_db()
    for nombre, valor in mocks.items():
        monkeypatch.setattr(web.svc, nombre, valor)
    return TestClient(app, base_url="http://localhost", headers={"Origin": "http://localhost"})


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_lista_vacia_y_llena(monkeypatch):
    monkeypatch.setattr(web, "_destinos_por_id", AsyncMock(return_value={}))
    monkeypatch.setattr(web, "_declaraciones", AsyncMock(return_value=({}, {})))
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]))
    try:
        r = c.get("/ui/pendientes/carpetas/correspondencias")
        assert r.status_code == 200 and "Todavía no has creado ninguna correspondencia." in r.text
        assert r.headers["cache-control"] == "no-store"
    finally:
        _cerrar()
    corr = _corr()
    d = SimpleNamespace(id=corr.declaracion_version_id, declaracion_id=uuid4(),
                        estado=EstadoRegla.ACTIVA)
    monkeypatch.setattr(web, "_destinos_por_id", AsyncMock(return_value={}))
    monkeypatch.setattr(web, "_declaraciones", AsyncMock(return_value=({d.id: d}, {d.declaracion_id: d})))
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[corr]))
    try:
        r = c.get("/ui/pendientes/carpetas/correspondencias")
    finally:
        _cerrar()
    assert "Activas (1)" in r.text and "Versión 1" in r.text
    assert "Destino no disponible" in r.text  # no hay fila real de destino en el fake
    assert "Cambiar" in r.text and "Desactivar" in r.text


def test_crear_confirmacion_no_escribe(monkeypatch):
    decl = _decl()
    crear = AsyncMock()
    monkeypatch.setattr(web, "_declaracion_activa", AsyncMock(return_value=decl))
    monkeypatch.setattr(web, "_destinos_por_id", AsyncMock(return_value={
        uuid4(): None}))
    # destino falso con id conocido
    from zascarr.web.correspondencias_contexto import DestinoVista
    did = uuid4()
    destino = DestinoVista(TipoDestino.SERIE, did, "Serie «Batman» (2019)", "")
    monkeypatch.setattr(web, "_destinos_por_id", AsyncMock(return_value={did: destino}))
    c = _cliente(monkeypatch, crear=crear)
    try:
        r = c.post("/ui/pendientes/carpetas/correspondencias/crear",
                   data={"declaracion": str(decl.id), "tipo": "serie", "destino_id": str(did),
                         "tipo_registro": "archivo"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "Vas a crear una correspondencia" in r.text
    assert "no vincula archivos" in r.text
    crear.assert_not_awaited()
    c = _cliente(monkeypatch, crear=crear)
    try:
        r = c.post("/ui/pendientes/carpetas/correspondencias/crear",
                   data={"declaracion": str(decl.id), "tipo": "serie", "destino_id": str(did),
                         "tipo_registro": "archivo", "confirmado": "1"},
                   follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and "aviso=creada" in r.headers["location"]
    assert r.headers["cache-control"] == "no-store"
    crear.assert_awaited_once()


def test_propuesta_disponible_muestra_traza_sin_aplicar(monkeypatch):
    from zascarr.services.correspondencias_contexto import Propuesta
    p = Propuesta(correspondencia_id=uuid4(), version_de_regla=2, declaracion_id=uuid4(),
                  version_declaracion=1, destino_tipo=TipoDestino.SERIE, destino_id=uuid4(),
                  alcance={"contexto_raiz": "Comics/A", "incluir_descendientes": False,
                           "tipo_de_registro": "archivo"},
                  origen=OrigenRegla.LOCAL, precedencia_aplicada="local", evidencia={})
    resultado = ResultadoEvaluacion(EstadoEvaluacion.PROPUESTA_DISPONIBLE, "Hay una propuesta.",
                                    propuesta=p, correspondencia_id=p.correspondencia_id,
                                    version_de_regla=2, destino_tipo=TipoDestino.SERIE,
                                    destino_id=p.destino_id, alcance=p.alcance,
                                    version_declaracion=1)
    monkeypatch.setattr(web.svc, "evaluar", AsyncMock(return_value=resultado))
    monkeypatch.setattr(web, "_destinos_por_id", AsyncMock(return_value={}))
    c = _cliente(monkeypatch)
    try:
        r = c.get("/ui/pendientes/carpetas/contexto/propuesta?clave=Comics%2FA")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Propuesta disponible" in r.text and "Identidad y versión de la regla" in r.text
    assert str(p.correspondencia_id) in r.text and "Versión de la regla: 2" in r.text
    assert "aplicar" not in r.text.lower() or "no se aplica" in r.text.lower()


def test_propuesta_fuera_alcance_y_conflicto(monkeypatch):
    fuera = ResultadoEvaluacion(EstadoEvaluacion.FUERA_DE_ALCANCE,
                                "Ninguna correspondencia activa cubre esta carpeta.")
    monkeypatch.setattr(web.svc, "evaluar", AsyncMock(return_value=fuera))
    c = _cliente(monkeypatch)
    try:
        r = c.get("/ui/pendientes/carpetas/contexto/propuesta?clave=Comics%2FA")
    finally:
        _cerrar()
    assert "Fuera de alcance" in r.text and "No se usa el parecido del nombre" in r.text


def test_ciclo_correspondencia(monkeypatch):
    corr = _corr()
    monkeypatch.setattr(web, "_destinos_por_id", AsyncMock(return_value={}))
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[corr]),
                 desactivar=AsyncMock(), activar=AsyncMock(), retirar=AsyncMock())
    try:
        assert c.post(f"/ui/pendientes/carpetas/correspondencias/desactivar/{corr.correspondencia_id}", follow_redirects=False).status_code == 303
        assert c.post(f"/ui/pendientes/carpetas/correspondencias/reactivar/{corr.correspondencia_id}", follow_redirects=False).status_code == 303
        assert c.get(f"/ui/pendientes/carpetas/correspondencias/retirar/{corr.correspondencia_id}").status_code == 200
        assert c.post(f"/ui/pendientes/carpetas/correspondencias/retirar/{corr.correspondencia_id}", follow_redirects=False).status_code == 303
    finally:
        _cerrar()
