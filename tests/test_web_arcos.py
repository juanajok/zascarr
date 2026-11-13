"""BL-C4 (#151): pantallas de sagas (servicio sustituido)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.arcos import ArcoResumen, DetalleArco, FilaArco, PaginaArcos


def _cliente(metadata=None):
    """Cliente con una BD falsa: `execute` devuelve el `metadata_` del arco (o None)."""
    async def _execute(_consulta):
        return SimpleNamespace(scalar_one_or_none=lambda: metadata)

    async def _db():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(),
                              execute=_execute)
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def test_lista_de_sagas_muestra_orden_y_salto_de_series():
    pagina = PaginaArcos(
        [ArcoResumen("a1", "Court of Owls", True, 2, 2)], 1, 1, 1, 0, 1)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(return_value=pagina)):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert "Court of Owls" in r.text and "2 series" in r.text


def test_detalle_lista_en_orden_de_lectura():
    filas = [
        FilaArco(1, "i1", "s1", "Batman", "1", None, "2011-01-01", True),
        FilaArco(2, "i2", "s2", "Nightwing", "2", None, None, False),
    ]
    detalle = DetalleArco("a1", "Court of Owls", "Sinopsis", True, filas, 2)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert r.text.index("Batman") < r.text.index("Nightwing")
    assert "En tu biblioteca" in r.text and "No disponible" in r.text


def test_detalle_de_saga_atribuye_a_fandom_con_articulo_y_licencia():
    """SCR2 (AC-03/AC-16): un arco creado por el enricher enlaza su página y la licencia."""
    detalle = DetalleArco("a1", "Year One", None, False, [], 0)
    c = _cliente(metadata={"origen": "fandom_dc", "fandom_dc": "Batman: Year One"})
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200
    assert 'href="https://dc.fandom.com/wiki/Batman:_Year_One"' in r.text
    assert 'href="https://creativecommons.org/licenses/by-sa/3.0/"' in r.text
    assert "DC Database" in r.text and "Creative Commons BY-SA 3.0" in r.text


def test_detalle_de_saga_manual_no_atribuye_a_fandom():
    detalle = DetalleArco("a1", "Saga mía", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            r = c.get(f"/ui/arcos/{uuid4()}")
    finally:
        _cerrar()
    assert r.status_code == 200 and "creativecommons.org" not in r.text


def test_saga_sin_datos_muestra_estado_vacio():
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.listar_arcos", AsyncMock(
                return_value=PaginaArcos([], 0, 1, 1, 0, 0))):
            r = c.get("/ui/arcos")
    finally:
        _cerrar()
    assert r.status_code == 200 and "Todavía no hay sagas" in r.text


def test_formularios_crud_y_redirecciones(monkeypatch):
    from zascarr.services.arcos import DetalleArco, ResultadoArco

    arco = SimpleNamespace(id=uuid4(), title="Saga", description=None,
                           is_crossover=False)
    detalle = DetalleArco(str(arco.id), "Saga", None, False, [], 0)
    c = _cliente()
    try:
        with patch("zascarr.web.arcos.crear_arco", AsyncMock(
                return_value=ResultadoArco(True, arco=arco))):
            r = c.post("/ui/arcos/nueva", data={"title": "Saga"},
                       follow_redirects=False)
        assert r.status_code == 303 and str(arco.id) in r.headers["location"]
        with patch("zascarr.web.arcos.detalle_arco", AsyncMock(return_value=detalle)):
            assert c.get(f"/ui/arcos/{arco.id}/editar").status_code == 200
            assert c.get(f"/ui/arcos/{arco.id}/eliminar").status_code == 200
        with patch("zascarr.web.arcos.agregar_numero", AsyncMock(
                return_value=ResultadoArco(True, arco=arco))):
            r = c.post(f"/ui/arcos/{arco.id}/numeros",
                       data={"serie": "Batman", "numero": "1"},
                       follow_redirects=False)
        assert r.status_code == 303
    finally:
        _cerrar()
