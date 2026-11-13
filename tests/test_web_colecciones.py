"""#155/BL-D6: UI de colecciones (servicio sustituido, sin BD)."""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.colecciones import (
    ColeccionResumen,
    DetalleColeccion,
    ResultadoColeccion,
    SerieDeColeccion,
)
from zascarr.services.portada_coleccion import CandidataPortada, ResultadoEleccion, ResultadoPortada


def _cliente():
    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_lista_muestra_colecciones_y_politica():
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.listar_colecciones", AsyncMock(return_value=[
                ColeccionResumen("c1", "Grapas", "En curso", "incluir", 2,
                                 tiene_portada=True,
                                 portada_url="/ui/colecciones/c1/portada?v=auto-abc")])):
            r = c.get("/ui/colecciones")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Grapas" in r.text and "Buscar faltantes de todas" in r.text
    assert "No buscar automáticamente" in r.text and "(heredar)" not in r.text
    assert "/ui/colecciones/c1/portada?v=auto-abc" in r.text
    assert "?v=" in r.text
    assert "Nueva colección" in r.text


def test_detalle_muestra_series_y_selector():
    c = _cliente()
    detalle = DetalleColeccion("c1", "Grapas", "En curso", "excluir",
                               [SerieDeColeccion(
                                   "s1", "Flash", 1987, "faltantes",
                                   "Buscar los números que faltan", "ninguno",
                                   "No buscar automáticamente")])
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[
                 SerieDeColeccion("s2", "Batman", 1940, "ninguno")])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[
                 CandidataPortada("s1", "Flash", True)])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[
                 {"run_id": "run123456789", "fecha": datetime(2026, 11, 13, 10, 0, tzinfo=UTC),
                  "materializados": 2, "saltados": 0, "errores": 0, "modo": "hardlink"}])):
            cid = uuid4()
            r = c.get(f"/ui/colecciones/{cid}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Flash" in r.text and "Batman" in r.text
    assert "Elegir portada" in r.text and "Usar la automática" in r.text
    assert "/portada" in r.text
    assert "Guardada: Buscar los números que faltan" in r.text
    assert "Efectiva: No buscar automáticamente" in r.text
    assert "No buscar automáticamente" in r.text
    assert "Borrar esta colección" in r.text
    assert "confirm(" not in r.text
    assert ">ninguno<" not in r.text and ">heredar<" not in r.text
    assert 'id="exportaciones"' in r.text and "run123456789" in r.text


def test_crear_valida_y_redirige():
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.crear_coleccion", AsyncMock(
                return_value=ResultadoColeccion(
                    False, {"name": "El nombre no puede estar vacío."}))), \
             patch("zascarr.web.colecciones.listar_colecciones", AsyncMock(return_value=[])):
            r = c.post("/ui/colecciones/nueva", data={"name": "", "description": "",
                                                       "auto_search": "heredar"})
        assert r.status_code == 200 and "El nombre no puede estar vacío." in r.text
        with patch("zascarr.web.colecciones.crear_coleccion", AsyncMock(
                return_value=ResultadoColeccion(True, coleccion=SimpleNamespace(id=uuid4())))):
            r = c.post("/ui/colecciones/nueva", data={"name": "Grapas", "description": "",
                                                       "auto_search": "incluir"},
                       follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].endswith("guardado=creada")
    finally:
        _cerrar()


def test_editar_asignar_quitar_y_borrar_redirigen():
    c = _cliente()
    coleccion = SimpleNamespace(id=uuid4())
    detalle = DetalleColeccion(str(coleccion.id), "Grapas", None, "heredar", [])
    try:
        with patch("zascarr.web.colecciones.editar_coleccion", AsyncMock(
                return_value=ResultadoColeccion(True, coleccion=coleccion))):
            r = c.post(f"/ui/colecciones/{coleccion.id}/editar",
                       data={"name": "Otra", "description": "", "auto_search": "excluir"},
                       follow_redirects=False)
        assert r.status_code == 303 and "guardado=guardada" in r.headers["location"]
        with patch("zascarr.web.colecciones.asignar_series", AsyncMock(
                return_value=ResultadoColeccion(True, coleccion=coleccion))):
            r = c.post(f"/ui/colecciones/{coleccion.id}/series",
                       data={"serie_ids": [str(uuid4()), str(uuid4())]},
                       follow_redirects=False)
        assert r.status_code == 303 and "guardado=asignadas" in r.headers["location"]
        with patch("zascarr.web.colecciones.quitar_serie", AsyncMock(return_value=True)):
            r = c.post(f"/ui/colecciones/{coleccion.id}/series/{uuid4()}/quitar",
                       follow_redirects=False)
        assert r.status_code == 303 and "guardado=quitada" in r.headers["location"]
        with patch("zascarr.web.colecciones.borrar_coleccion", AsyncMock(return_value=True)):
            r = c.post(f"/ui/colecciones/{coleccion.id}/borrar", follow_redirects=False)
        assert r.status_code == 303 and "guardado=borrada" in r.headers["location"]
        del detalle
    finally:
        _cerrar()


def test_endpoint_portada_etag_304_y_404():
    cid = uuid4()
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.obtener_portada", AsyncMock(
                return_value=ResultadoPortada(b"jpeg", etag='"abc"'))):
            r = c.get(f"/ui/colecciones/{cid}/portada")
            r304 = c.get(f"/ui/colecciones/{cid}/portada",
                         headers={"If-None-Match": '"abc"'})
        assert r.status_code == 200 and r.content == b"jpeg"
        assert r.headers["etag"] == '"abc"' and "private" in r.headers["cache-control"]
        assert r304.status_code == 304
        with patch("zascarr.web.colecciones.obtener_portada", AsyncMock(return_value=None)):
            r404 = c.get(f"/ui/colecciones/{cid}/portada")
        assert r404.status_code == 404 and r404.headers["cache-control"] == "no-store"
    finally:
        _cerrar()


def test_panel_elegir_portada_post():
    cid = uuid4()
    sid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.elegir_portada", AsyncMock(
                 return_value=ResultadoEleccion(True, {}))):
            r = c.post(f"/ui/colecciones/{cid}/portada", data={"series_id": str(sid)},
                       follow_redirects=False)
        assert r.status_code == 303 and "guardado=portada" in r.headers["location"]
    finally:
        _cerrar()


def test_panel_uuid_invalido_no_llama_a_elegir():
    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    c = _cliente()
    llamada = AsyncMock()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.elegir_portada", llamada):
            r = c.post(f"/ui/colecciones/{cid}/portada", data={"series_id": "no-uuid"})
    finally:
        _cerrar()
    assert r.status_code == 200 and "no es válida" in r.text
    llamada.assert_not_awaited()


def test_aviso_portada_tras_elegir_y_fallback_sin_img():
    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [],
                               tiene_portada=False,
                               portada_url=f"/ui/colecciones/{cid}/portada?v=auto")
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])):
            r = c.get(f"/ui/colecciones/{cid}?guardado=portada")
    finally:
        _cerrar()
    assert "Portada actualizada." in r.text
    assert "autofocus" in r.text
    # Sin portada cacheada no se emite un <img> que daría 404.
    assert f'src="/ui/colecciones/{cid}/portada' not in r.text


def test_multiseleccion_muestra_checkboxes_y_redirige():
    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    s1, s2 = str(uuid4()), str(uuid4())
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[
                 SerieDeColeccion(s1, "Flash", 1987, "ninguno"),
                 SerieDeColeccion(s2, "Batman", 1940, "ninguno")])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.asignar_series", AsyncMock(
                 return_value=ResultadoColeccion(True))):
            r = c.get(f"/ui/colecciones/{cid}")
            assert r.status_code == 200
            assert 'name="serie_ids"' in r.text and "Añadir series seleccionadas" in r.text
            assert 'name="serie_ids" value="' + s1 + '"' in r.text
            r2 = c.post(f"/ui/colecciones/{cid}/series",
                        data={"serie_ids": [s1, s2]}, follow_redirects=False)
        assert r2.status_code == 303 and "guardado=asignadas" in r2.headers["location"]
    finally:
        _cerrar()


def test_multiseleccion_uuid_invalido_no_llama_al_servicio():
    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    valida = str(uuid4())
    c = _cliente()
    llamada = AsyncMock()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[
                 SerieDeColeccion(valida, "Flash", 1987, "ninguno")])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.asignar_series", llamada):
            r = c.post(f"/ui/colecciones/{cid}/series",
                       data={"serie_ids": [valida, "no-uuid"]})
    finally:
        _cerrar()
    assert r.status_code == 200 and "no es válida" in r.text
    assert f'value="{valida}"' in r.text and "checked" in r.text
    llamada.assert_not_awaited()


def test_filtros_y_seleccion_oculta_en_plantilla():
    cid = uuid4()
    visible, oculta = str(uuid4()), str(uuid4())
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[
                 SerieDeColeccion(visible, "Flash", 1987, "ninguno")])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])):
            r = c.get(f"/ui/colecciones/{cid}", params=[
                ("q", "flash"), ("tradicion", "american"),
                ("serie_ids", visible), ("serie_ids", oculta)])
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'name="q"' in r.text and 'name="tradicion"' in r.text
    assert "1 serie disponible" in r.text
    assert f'name="serie_ids" value="{oculta}"' in r.text
    assert f'value="{visible}"' in r.text and "checked" in r.text


def test_filtro_sin_resultados_ofrece_limpiar():
    cid = uuid4()
    detalle = DetalleColeccion(str(cid), "Grapas", None, "heredar", [])
    c = _cliente()
    try:
        with patch("zascarr.web.colecciones.detalle_coleccion", AsyncMock(return_value=detalle)), \
             patch("zascarr.web.colecciones.series_sin_coleccion", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.candidatas_portada", AsyncMock(return_value=[])), \
             patch("zascarr.web.colecciones.historial_exportaciones", AsyncMock(return_value=[])):
            r = c.get(f"/ui/colecciones/{cid}", params={"q": "nada"})
    finally:
        _cerrar()
    assert "No hay series con esos filtros" in r.text and "Limpiar filtros" in r.text
