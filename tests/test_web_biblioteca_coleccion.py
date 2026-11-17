"""#340: filtro de estado de colección en Biblioteca (combinable y retirable)."""
from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import Series
from zascarr.web import library


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def scalars(self):
        return self

    def all(self):
        return self._filas

    def scalar(self):
        return self._filas


class _Sesion:
    async def execute(self, _stmt):
        return _Resultado([])


class _Servicio:
    llamadas: list[dict] = []

    def __init__(self, _db):
        pass

    async def list_publishers_with_series(self):
        return []

    async def list_series_paginado(self, **kwargs):
        type(self).llamadas.append(kwargs)
        serie = Series(id=uuid4(), title="Thorgal", tradition="american")
        serie.lectura_leidos = 0
        serie.lectura_total = 0
        return [serie], 1, 1

    async def nombres_de_filtros(self, **_kwargs):
        return {}


def _contexto(monkeypatch):
    monkeypatch.setattr(library, "SeriesService", _Servicio)
    _Servicio.llamadas = []

    async def _db():
        yield _Sesion()

    app.dependency_overrides[get_db] = _db


def test_filtro_coleccion_se_combina_y_se_puede_quitar(monkeypatch):
    _contexto(monkeypatch)
    try:
        r = TestClient(app).get(
            "/ui/biblioteca?coleccion=faltan&q=Thorgal&tradition=american")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.headers.get("cache-control") == "no-store"
    kwargs = _Servicio.llamadas[0]
    assert kwargs["search"] == "Thorgal"
    assert kwargs["tradition"] == "american"
    assert kwargs["coleccion"] == "faltan"
    assert 'value="faltan" selected' in r.text
    assert "Te faltan números" in r.text
    assert "Quitar filtro: Te faltan números" in r.text
    assert "coleccion=faltan" in r.text
    assert '<label for="f-coleccion">Estado de la serie</label>' in r.text
    # El chip de quitar conserva los demás filtros y pierde solo coleccion.
    quitar = r.text.split("Quitar filtro: Te faltan números", 1)[0].rsplit("href=\"", 1)[1]
    assert "q=Thorgal" in quitar and "tradition=american" in quitar
    assert "coleccion=faltan" not in quitar


def test_selector_fuera_de_rejilla_se_actualiza_por_oob(monkeypatch):
    _contexto(monkeypatch)
    try:
        # La página trae el select en el formulario; el fragmento HTMX lo
        # devuelve OOB para que no se quede con el valor anterior.
        fragmento = TestClient(app).get(
            "/ui/biblioteca/resultados?quitar=coleccion",
            headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert fragmento.status_code == 200
    assert 'id="f-coleccion" hx-swap-oob="outerHTML"' in fragmento.text
    assert 'aria-label="Estado de la serie"' in fragmento.text
    assert '<option value="">Cualquier estado</option>' in fragmento.text
    assert 'selected' not in fragmento.text.split('hx-swap-oob="outerHTML"', 1)[1]

    # «Limpiar todos» también actualiza el selector aunque no hubiera colección.
    _contexto(monkeypatch)
    try:
        limpiar = TestClient(app).get(
            "/ui/biblioteca/resultados?quitar=todos",
            headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert 'id="f-coleccion" hx-swap-oob="outerHTML"' in limpiar.text
    assert 'selected' not in limpiar.text.split('id="f-coleccion" hx-swap-oob="outerHTML"', 1)[1]
    assert fragmento.headers.get("cache-control") == "no-store"


def test_coleccion_invalida_se_descarta_con_aviso(monkeypatch):
    _contexto(monkeypatch)
    try:
        r = TestClient(app).get("/ui/biblioteca?coleccion=inventado")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "El filtro de estado de colección no es válido" in r.text


def test_filtros_puros_normalizan_y_omiten_coleccion():
    filtros = library._leer_filtros(1, "", "", "", "", "", "", "", "", coleccion="no_completar")
    assert filtros.coleccion == "no_completar"
    qs = library._qs(filtros, page=1)
    assert "coleccion=no_completar" in qs
    assert "coleccion" not in library._qs(filtros, page=1, omitir="coleccion")
