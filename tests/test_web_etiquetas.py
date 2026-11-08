# ruff: noqa: E501
"""
tests/test_web_etiquetas.py

Rutas de etiquetas de la ficha de serie (BL-ETQ1a, #403): sugerir, añadir, quitar y crear.
Fragmentos HTML (nunca JSON), avisos exactos, `Cache-Control: no-store`, mass assignment y XSS.
Usa sesión falsa con colas (mismo patrón que test_web_series.py); la lógica de dominio se cubre
en test_etiquetas_service.py y la BD real en los tests `*_pg`.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app


class FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeExecResult:
    def __init__(self, rows):
        self._rows = rows

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalars(self):
        return FakeScalarResult(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class FakeSession:
    def __init__(self, queue):
        self._queue = list(queue)
        self.flush = AsyncMock()
        self.added: list = []

    async def execute(self, _statement):
        return self._queue.pop(0)

    def add(self, obj):
        self.added.append(obj)


def override_get_db(session):
    async def _get_db():
        yield session
    return _get_db


def use_fake_session(session):
    class _Ctx:
        def __enter__(self):
            app.dependency_overrides[get_db] = override_get_db(session)
            return TestClient(app)

        def __exit__(self, *exc):
            app.dependency_overrides.pop(get_db, None)
    return _Ctx()


def _tag(clave="noir"):
    return SimpleNamespace(id=uuid4(), clave=clave)


def _asignacion(source="manual", oculta=False):
    return SimpleNamespace(source=source, oculta=oculta)


SERIE = uuid4()


class TestSugerir:

    def test_sugiere_con_recuento_y_boton(self):
        session = FakeSession([FakeExecResult([("noir", 34)])])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{SERIE}/etiquetas/sugerir?etiqueta=noir")
        assert r.status_code == 200
        assert r.headers["Cache-Control"] == "no-store"
        assert "noir" in r.text
        assert "34 series" in r.text
        assert "Añadir" in r.text
        assert f"/ui/series/{SERIE}/etiquetas" in r.text

    def test_nombre_nuevo_ofrece_crear(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{SERIE}/etiquetas/sugerir?etiqueta=noirx")
        assert "Crear «noirx»" in r.text
        assert 'name="crear" value="1"' in r.text

    def test_menos_de_dos_caracteres_no_consulta_y_devuelve_vacio(self):
        session = FakeSession([])  # si consultara, estallaría
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{SERIE}/etiquetas/sugerir?etiqueta=n")
        assert r.status_code == 200
        assert r.headers["Cache-Control"] == "no-store"
        assert r.text.strip() == ""

    def test_sin_coincidencias_y_nombre_no_creable_dice_el_vacio(self):
        """Un texto que normaliza a vacío no es un nombre creable (D-6): se enseña el vacío."""
        session = FakeSession([])
        with use_fake_session(session) as client:
            r = client.get(f"/ui/series/{SERIE}/etiquetas/sugerir?etiqueta=!!")
        assert "Sin coincidencias. Prueba con otras letras." in r.text
        assert "Crear" not in r.text


class TestAnadir:

    def test_anade_y_muestra_el_chip(self):
        tag = _tag("noir")
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([tag]), FakeExecResult([]),
            FakeExecResult(None), FakeExecResult([tag]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={"etiqueta": "noir"})
        assert r.status_code == 200
        assert r.headers["Cache-Control"] == "no-store"
        assert "Etiqueta añadida." in r.text
        assert "noir" in r.text

    def test_duplicada_da_aviso(self):
        tag = _tag("noir")
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([tag]), FakeExecResult([_asignacion()]),
            FakeExecResult([tag]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={"etiqueta": "noir"})
        assert "Esa etiqueta ya estaba en la serie." in r.text

    def test_inexistente_sin_crear_da_aviso(self):
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([]), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={"etiqueta": "noirx"})
        assert "Esa etiqueta no existe. Elige una de las sugerencias." in r.text

    def test_crear_crea_y_anade(self):
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([]), FakeExecResult([]),
            FakeExecResult(None), FakeExecResult([_tag("noirx")]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={"etiqueta": "noirx", "crear": "1"})
        assert r.status_code == 200
        assert "Etiqueta añadida." in r.text
        assert "noirx" in r.text
        assert len(session.added) == 1 and session.added[0].name == "noirx"

    def test_crear_un_nombre_existente_da_ya_existe(self):
        tag = _tag("noir")
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([tag]), FakeExecResult([tag]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={"etiqueta": "Nóir", "crear": "1"})
        assert "Esa etiqueta ya existe: noir" in r.text

    def test_mass_assignment_solo_cuenta_etiqueta(self):
        """`source`/`weight`/`namespace` inyectados se ignoran: la ruta solo declara `etiqueta` y `crear`."""
        tag = _tag("noir")
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([tag]), FakeExecResult([]),
            FakeExecResult(None), FakeExecResult([tag]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={
                "etiqueta": "noir", "source": "comic_vine", "weight": "100", "namespace": "genero",
            })
        assert r.status_code == 200
        assert "Etiqueta añadida." in r.text

    def test_sin_etiqueta_da_422(self):
        session = FakeSession([FakeExecResult([SERIE])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={})
        assert r.status_code == 422

    def test_nombre_con_html_no_se_ejecuta(self):
        """El nombre se normaliza (se van `<`, `>`, `=`, `(`, `)`…) y el chip se escapa: sin `<script>`."""
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([]), FakeExecResult([]),
            FakeExecResult(None), FakeExecResult([_tag("script-alert-1-script")]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={
                "etiqueta": "<script>alert(1)</script>", "crear": "1",
            })
        assert r.status_code == 200
        assert "<script>" not in r.text
        assert "script-alert-1-script" in r.text

    def test_serie_inexistente_da_aviso_sin_romper_el_swap(self):
        session = FakeSession([FakeExecResult([])])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas", data={"etiqueta": "noir"})
        assert r.status_code == 200
        assert "No se pudo guardar. Vuelve a intentarlo." in r.text


class TestQuitar:

    def test_quitar_manual_borra_y_avisa(self):
        tag = _tag("noir")
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([tag]), FakeExecResult([_asignacion()]),
            FakeExecResult(None), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas/quitar", data={"etiqueta": "noir"})
        assert r.status_code == 200
        assert r.headers["Cache-Control"] == "no-store"
        assert "Etiqueta quitada." in r.text

    def test_quitar_una_fila_de_fuente_la_oculta(self):
        tag = _tag("noir")
        session = FakeSession([
            FakeExecResult([SERIE]), FakeExecResult([tag]),
            FakeExecResult([_asignacion(source="comicinfo_xml")]),
            FakeExecResult(None), FakeExecResult([]),
        ])
        with use_fake_session(session) as client:
            r = client.post(f"/ui/series/{SERIE}/etiquetas/quitar", data={"etiqueta": "noir"})
        assert "Etiqueta quitada." in r.text
