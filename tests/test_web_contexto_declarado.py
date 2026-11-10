# ruff: noqa: E501
"""MIT-M7 130-b: rutas y pantallas de declaraciones (sin navegador)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import EstadoRegla, OrigenRegla, TipoSignificadoCarpeta
from zascarr.services.declaraciones_carpeta import DeclaracionVista
from zascarr.web import contexto_declarado as web


def _vista(*, estado=EstadoRegla.ACTIVA, origen=OrigenRegla.LOCAL,
           tipo=TipoSignificadoCarpeta.AUTOR, incluir=False, version=1,
           ruta="Comics/Carlos Giménez"):
    return DeclaracionVista(
        id=uuid4(), declaracion_id=uuid4(), version=version, contexto_raiz=ruta,
        incluir_descendientes=incluir, tipo_de_significado=tipo, origen=origen,
        estado=estado, vigente_desde=datetime.now(UTC), vigente_hasta=None,
        procedencia={})


def _get_db():
    async def _db():
        yield SimpleNamespace()
    return _db


def _cliente(monkeypatch, **mocks):
    app.dependency_overrides[get_db] = _get_db()
    for nombre, valor in mocks.items():
        monkeypatch.setattr(web.svc, nombre, valor)
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_lista_vacia_y_textos(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]))
    try:
        r = c.get("/ui/pendientes/carpetas/contexto")
    finally:
        _cerrar()
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert "Todavía no has declarado ninguna carpeta." in r.text
    assert "no crean series ni tocan archivos" in r.text


def test_lista_tarjeta_activa_y_acciones(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[_vista()]))
    try:
        r = c.get("/ui/pendientes/carpetas/contexto")
    finally:
        _cerrar()
    assert "Activas (1)" in r.text and "Por autor" in r.text and "Local" in r.text
    assert "Versión 1" in r.text and "Solo esta carpeta" in r.text
    assert "Cambiar" in r.text and "Desactivar" in r.text and "Retirar" in r.text


def test_formulario_sin_preseleccion_y_error_sin_tipo(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]))
    try:
        r = c.get("/ui/pendientes/carpetas/declarar?clave=Comics%2FCarlos+Gim%C3%A9nez")
        assert r.status_code == 200
        assert "Por autor" in r.text and "Por publicación" in r.text
        assert "checked" not in r.text.split('name="tipo"')[1].split("</fieldset>")[0]
        assert "No crea series, no mueve archivos" in r.text
        r2 = c.post("/ui/pendientes/carpetas/declarar", data={"clave": "Comics/A"})
    finally:
        _cerrar()
    assert r2.status_code == 200
    assert "Elige qué significa la carpeta antes de guardar." in r2.text


def test_confirmacion_alcance_no_escribe(monkeypatch):
    decl = AsyncMock()
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]), declarar=decl)
    try:
        r = c.post("/ui/pendientes/carpetas/declarar",
                   data={"clave": "Comics/A", "tipo": "autor", "incluir": "1"})
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Vas a incluir también las subcarpetas." in r.text
    assert "Sí, incluir subcarpetas" in r.text
    decl.assert_not_awaited()


def test_confirmado_crea_y_redirige(monkeypatch):
    decl = AsyncMock()
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]), declarar=decl)
    try:
        r = c.post("/ui/pendientes/carpetas/declarar",
                   data={"clave": "Comics/A", "tipo": "autor", "incluir": "1", "confirmado": "1"},
                   follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and r.headers["location"].endswith("contexto?aviso=guardada")
    assert r.headers["cache-control"] == "no-store"
    decl.assert_awaited_once()


def test_carpeta_ya_activa_no_pinta_formulario(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[_vista()]))
    try:
        r = c.get("/ui/pendientes/carpetas/declarar?clave=Comics%2FCarlos+Gim%C3%A9nez")
    finally:
        _cerrar()
    assert "Esta carpeta ya tiene una declaración activa." in r.text
    assert "Guardar declaración" not in r.text
    assert "Cambiar declaración" in r.text


def test_importacion_no_se_presenta_como_local(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[_vista(origen=OrigenRegla.IMPORTACION)]))
    try:
        r = c.get("/ui/pendientes/carpetas/declarar?clave=Comics%2FCarlos+Gim%C3%A9nez")
    finally:
        _cerrar()
    assert "no es una decisión local" in r.text
    assert "Guardar declaración" in r.text


def test_ruta_invalida_y_raiz_sin_formulario(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]))
    try:
        r = c.get("/ui/pendientes/carpetas/declarar?clave=..%2Ffuera")
        r2 = c.get("/ui/pendientes/carpetas/declarar?clave=")
    finally:
        _cerrar()
    assert r.status_code == 200 and "La ruta de esta carpeta no es válida." in r.text
    assert "No sabemos qué carpeta quieres declarar." in r2.text
    assert "<form" not in r.text


def test_cambiar_reducir_y_desactivar_reactivar_retirar(monkeypatch):
    d = _vista(incluir=True, version=2)
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[d]),
                 historial=AsyncMock(return_value=[d]),
                 cambiar=AsyncMock(return_value=d),
                 desactivar=AsyncMock(return_value=d),
                 reactivar=AsyncMock(return_value=d),
                 retirar=AsyncMock(return_value=d))
    try:
        assert c.get(f"/ui/pendientes/carpetas/cambiar/{d.id}").status_code == 200
        r = c.post(f"/ui/pendientes/carpetas/cambiar/{d.id}",
                   data={"tipo": "publicacion", "incluir": "0"},
                   follow_redirects=False)
        assert r.status_code == 303
        assert c.post(f"/ui/pendientes/carpetas/desactivar/{d.id}", follow_redirects=False).status_code == 303
        assert c.post(f"/ui/pendientes/carpetas/reactivar/{d.id}", follow_redirects=False).status_code == 303
        assert c.get(f"/ui/pendientes/carpetas/retirar/{d.id}").status_code == 200
        assert c.post(f"/ui/pendientes/carpetas/retirar/{d.id}", follow_redirects=False).status_code == 303
    finally:
        _cerrar()


def test_retirada_no_se_reactiva(monkeypatch):
    d = _vista(estado=EstadoRegla.RETIRADA)
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[d]),
                 historial=AsyncMock(return_value=[d]))
    try:
        r = c.post(f"/ui/pendientes/carpetas/reactivar/{d.id}")
        r2 = c.get(f"/ui/pendientes/carpetas/cambiar/{d.id}")
    finally:
        _cerrar()
    assert "no se puede reactivar. Crea una declaración nueva" in r.text
    assert "Una declaración retirada no se puede cambiar." in r2.text


def test_cambio_que_amplia_pide_confirmacion(monkeypatch):
    d = _vista(incluir=False, version=2)
    cambiar = AsyncMock()
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[d]),
                 historial=AsyncMock(return_value=[d]), cambiar=cambiar)
    try:
        r = c.post(f"/ui/pendientes/carpetas/cambiar/{d.id}",
                   data={"tipo": "autor", "incluir": "1"})
    finally:
        _cerrar()
    assert "Confirmar el alcance" in r.text and "La versión anterior dejará de aplicarse" in r.text
    cambiar.assert_not_awaited()


def test_css_declaraciones_es_accesible_y_no_desborda():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    assert "min-height: 44px" in css
    assert ".acciones-declaracion { display: flex; flex-wrap: wrap;" in css
    assert ".declaracion-ruta { overflow-wrap: anywhere;" in css


def test_confirmacion_pone_el_foco_en_el_titulo(monkeypatch):
    c = _cliente(monkeypatch, listar=AsyncMock(return_value=[]))
    try:
        r = c.post("/ui/pendientes/carpetas/declarar",
                   data={"clave": "Comics/A", "tipo": "autor", "incluir": "1"})
    finally:
        _cerrar()
    assert '<h1 tabindex="-1" autofocus>Confirmar el alcance</h1>' in r.text
