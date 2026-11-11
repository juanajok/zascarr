"""MIT-M7-US03 (#132-b): pantalla «Decisiones reutilizables» (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.decisiones_reutilizables import Decision
from zascarr.web import decisiones_reutilizables as web


def _decision(tipo="alias_aprendido", estado="propuesto", importada=False, acciones=None):
    return Decision(
        tipo=tipo, id=uuid4(), fila_id=uuid4(), origen="aprendido" if tipo.startswith("alias")
        else "importacion" if importada else "local", estado=estado, version=2,
        contexto="Global (sin carpeta)", alcance="Global — patrón «patrulla x»",
        destino="La Patrulla-X", efectos="No se aplica hasta que lo actives.",
        precedencia=("Capa 1 · manda sobre alias." if tipo in ("declaracion", "correspondencia")
                     else "Capa 3 · no pisa decisiones locales."), historial=(),
        acciones=tuple(acciones if acciones is not None else ("activar", "retirar")),
        es_importada=importada)


def _cliente(filas):
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db
    return TestClient(app), filas


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_la_pantalla_muestra_inventario_y_filtros():
    filas = [_decision(), _decision(tipo="declaracion", estado="activa",
                                    importada=False, acciones=("cambiar", "desactivar", "retirar"))]
    c, filas = _cliente(filas)
    try:
        with patch.object(web, "listar_decisiones", AsyncMock(return_value=filas)):
            r = c.get("/ui/pendientes/carpetas/decisiones")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Decisiones reutilizables" in r.text
    assert 'name="tipo"' in r.text and 'name="carpeta"' in r.text
    assert "Alias aprendido" in r.text and "Declaración de carpeta" in r.text
    assert "Pendiente de activar" in r.text
    assert "Capa 3" in r.text and "Capa 1" in r.text
    assert "/decisiones/confirmar/alias_aprendido/" in r.text


def test_la_confirmacion_de_activar_alias_es_explicita():
    d = _decision()
    c, _ = _cliente([d])
    try:
        with patch.object(web, "listar_decisiones", AsyncMock(return_value=[d])):
            r = c.get("/ui/pendientes/carpetas/decisiones/confirmar/"
                      f"alias_aprendido/{d.id}/activar")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Activar alias" in r.text
    assert "no cambia lo ya decidido" in r.text
    assert (f'action="/ui/pendientes/carpetas/decisiones/accion/'
            f'alias_aprendido/{d.id}/activar"' in r.text)
    assert 'name="confirmado" value="1"' in r.text


def test_activar_alias_llama_al_servicio_con_confirmacion():
    d = _decision()
    c, _ = _cliente([d])
    try:
        with patch.object(web, "listar_decisiones", AsyncMock(return_value=[d])), \
             patch.object(web.alias_svc, "activar_local", AsyncMock()) as activar:
            r = c.post("/ui/pendientes/carpetas/decisiones/accion/"
                       f"alias_aprendido/{d.id}/activar",
                       data={"confirmado": "1"}, follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and "aviso=activada" in r.headers["location"]
    activar.assert_awaited_once()
    assert activar.await_args.kwargs["confirmado"] is True


def test_sin_confirmacion_no_activa_ni_toca_el_servicio():
    d = _decision()
    c, _ = _cliente([d])
    try:
        with patch.object(web, "listar_decisiones", AsyncMock(return_value=[d])), \
             patch.object(web.alias_svc, "activar_local", AsyncMock()) as activar:
            r = c.post("/ui/pendientes/carpetas/decisiones/accion/"
                       f"alias_aprendido/{d.id}/activar",
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and "error=" in r.headers["location"]
    assert not activar.called


def test_una_importada_no_se_gestiona_desde_aqui():
    d = _decision(tipo="declaracion", estado="activa", importada=True,
                  acciones=())
    c, _ = _cliente([d])
    try:
        with patch.object(web, "listar_decisiones", AsyncMock(return_value=[d])), \
             patch.object(web.decl_svc, "desactivar", AsyncMock()) as desactivar:
            r = c.post("/ui/pendientes/carpetas/decisiones/accion/"
                       f"declaracion/{d.id}/desactivar",
                       follow_redirects=False)
    finally:
        _cerrar()
    assert r.status_code == 303 and "error=" in r.headers["location"]
    assert not desactivar.called
