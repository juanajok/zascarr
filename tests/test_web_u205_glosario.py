# ruff: noqa: E501
"""#205 AC5: textos visibles del glosario U7 en Por revisar, Biblioteca y Estado."""
from __future__ import annotations

import re
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ComicTradition, File, FileFormat, Series
from zascarr.services.revision_carpetas import (
    ArchivoRevision,
    Grupo,
    Pagina,
    PatronDeNombres,
    RespuestaCarpetas,
    Totales,
)
from zascarr.web import pendientes as modulo_pendientes


class SesionVacia:
    async def execute(self, _statement):
        raise AssertionError("esta prueba no debe consultar la BD")

    async def get(self, _modelo, _clave):
        return None


def _cliente():
    async def _get_db():
        yield SesionVacia()
    app.dependency_overrides[get_db] = _get_db
    return TestClient(app)


def _cerrar():
    app.dependency_overrides.pop(get_db, None)


def visible(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"\{#.*?#\}", "", html, flags=re.S))).strip()


def _get(ruta: str) -> str:
    c = _cliente()
    try:
        return c.get(ruta).text
    finally:
        _cerrar()


def _pagina_pendientes(archivos):
    return SimpleNamespace(
        archivos=archivos, total=len(archivos), desde=1, hasta=len(archivos),
        hay_anterior=False, hay_siguiente=False,
    )


def test_por_revisar_usa_pendientes_y_no_archivos(monkeypatch):
    archivo = File(id=uuid4(), file_path="/lib/_Unsorted/x.cbz", file_name="x.cbz",
                   file_format=FileFormat.CBZ, metadata_={"match_status": "unsorted"})
    monkeypatch.setattr(modulo_pendientes.ReviewService, "pagina_de_pendientes",
                        lambda _self, **_kw: _async(_pagina_pendientes([archivo])))
    html = _get("/ui/pendientes")
    t = visible(html)
    assert "Pendientes que el sistema no supo clasificar solo." in t
    assert "resuelves varios pendientes con una sola decisión" in t
    assert "Ver los pendientes sueltos" in t
    assert "Archivos que el sistema" not in t
    assert "varios archivos" not in t
    assert "Ver los archivos sueltos" not in t


def _async(valor):
    async def _coro():
        return valor
    return _coro()


def test_sueltos_titulo_h1_error_y_vacio(monkeypatch):
    monkeypatch.setattr(modulo_pendientes.RevisionCarpetas, "pagina_de_sueltos",
                        lambda _self, **_kw: _async(SimpleNamespace(
                            archivos=[], total=0, total_a=0, desde=0, hasta=0,
                            hay_anterior=False, hay_siguiente=False)))
    html = _get("/ui/pendientes/sueltos")
    assert "<title>Pendientes sueltos — ZascArr</title>" in html
    assert "<h1>Pendientes sueltos</h1>" in html
    assert "No hay pendientes sueltos." in visible(html)
    assert "Archivos sueltos" not in html

    async def falla(_self, **_kw):
        raise RuntimeError("fallo simulado")

    monkeypatch.setattr(modulo_pendientes.RevisionCarpetas, "pagina_de_sueltos", falla)
    html = _get("/ui/pendientes/sueltos")
    assert "No se pudieron leer los pendientes sueltos" in visible(html)
    assert "Pendientes sueltos" in html


def _respuesta(grupos=None):
    return RespuestaCarpetas(
        generado="2026-11-14T00:00:00Z", pagina=Pagina(limite=50, desplazamiento=0),
        grupos=grupos or [],
        totales=Totales(sin_serie=0, serie_sugerida=0, grupos=0, candidata_inexistente=0,
                        carpetas_utiles=0, carpetas_utiles_sin_serie=0,
                        carpetas_utiles_serie_sugerida=0, sin_serie_en_carpetas=0,
                        sin_serie_sueltos=0, serie_sugerida_en_carpetas=0,
                        serie_sugerida_sueltos=0, sueltos=0),
    )


class _ServicioFalso:
    respuesta = _respuesta()

    def __init__(self, _db): ...
    async def carpetas(self, **_kw): return self.respuesta


class _BorradoresFalsos:
    def __init__(self, _db): ...
    async def listar(self): return {}


def _con_carpetas(monkeypatch, respuesta):
    _ServicioFalso.respuesta = respuesta
    monkeypatch.setattr(modulo_pendientes, "RevisionCarpetas", _ServicioFalso)
    monkeypatch.setattr(modulo_pendientes, "BorradoresRevision", _BorradoresFalsos)

    async def _sin_serie(_db, _valor):
        return None, None
    monkeypatch.setattr(modulo_pendientes, "_serie_del_filtro", _sin_serie)


def test_carpetas_titulo_miga_y_vacio(monkeypatch):
    _con_carpetas(monkeypatch, _respuesta())
    html = _get("/ui/pendientes/carpetas")
    t = visible(html)
    assert "<title>Pendientes por carpeta — Por revisar — ZascArr</title>" in html
    assert "<h1>Pendientes por carpeta</h1>" in html
    assert "Por revisar › Pendientes por carpeta" in t
    assert "No hay pendientes por carpeta." in t
    assert "No hay registros pendientes" not in t


def test_carpetas_tarjeta_y_procedencia_conserva_registros(monkeypatch):
    grupo = Grupo(
        clave="Comics/Serie", carpeta_contextual="Serie", ascendentes=["Comics"],
        carpeta_limpia=None, estado="sin_serie", etiqueta="Sin serie", n_archivos=3,
        patron_de_nombres=PatronDeNombres(titulo_dominante=None, proporcion=0.0, titulos_distintos=0),
        serie_sugerida=None, por_confirmar=False, en_conflicto=False, senales=[],
        archivos=[ArchivoRevision(id="a", nombre="Serie 01.cbz", estado="sin_serie")],
    )
    respuesta = _respuesta([grupo])
    respuesta.totales.carpetas_utiles = 1
    respuesta.totales.sin_serie = 3
    _con_carpetas(monkeypatch, respuesta)
    html = _get("/ui/pendientes/carpetas")
    t = visible(html)
    assert "3 pendientes" in t
    assert "3 registros" not in t
    assert "Ver pendientes (1 de 3)" in t
    assert "Son registros pendientes de verificar, no archivos confirmados." in t
    assert "<dt>Pendientes</dt>" in html


def test_biblioteca_estado_de_la_serie_y_valores(monkeypatch):
    serie = Series(id=uuid4(), title="Batman", tradition=ComicTradition.AMERICAN)
    from tests.test_web_library import FakeExecResult, FakeSession, override_get_db
    session = FakeSession([FakeExecResult([]), FakeExecResult(1), FakeExecResult([serie])])
    app.dependency_overrides[get_db] = override_get_db(session)
    try:
        html = TestClient(app).get("/ui/biblioteca").text
    finally:
        _cerrar()
    assert "Estado de la serie" in html
    assert "Estado de la colección" not in html
    for valor in ("completa", "faltan", "no_calculable", "no_completar"):
        assert f'value="{valor}"' in html


from tests.test_web_estado_cortesia import cliente, entorno  # noqa: E402,F401


def test_estado_dice_tebeoteca(entorno, cliente):  # noqa: F811
    html = cliente.get("/estado").text
    assert "Descargar tebeoteca y deseados" in html
    assert "Descargar colección y deseados" not in html
