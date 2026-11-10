# ruff: noqa: E501
"""#150 BL-C3 web: guardar lectura, fragmento y filtro de biblioteca."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.main import app
from zascarr.models import ReadingStatus
from zascarr.services.lectura import EstadoLectura, ValoracionInvalidaError
from zascarr.web import series as web_series


def _estado(estado=ReadingStatus.COMPLETED, rating=4, nota="Muy bueno"):
    return EstadoLectura(str(uuid4()), estado, rating, nota, None, None)


def _override():
    async def _db():
        yield SimpleNamespace()
    app.dependency_overrides[get_db] = _db


def test_post_sin_js_redirige_y_no_store(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/leido",
                                 data={"estado": "completed", "rating": "4", "nota": "Muy bueno"},
                                 follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 303
    assert r.headers["location"].startswith(f"/ui/series/{sid}")
    assert r.headers["cache-control"] == "no-store"


def test_post_htmx_devuelve_control(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/leido",
                                 data={"estado": "completed"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "lectura-control" in r.text and "Leído" in r.text
    assert r.headers["cache-control"] == "no-store"


def test_valoracion_invalida_422(monkeypatch):
    _override()

    async def _marca(*_a, **_k):
        raise ValoracionInvalidaError("La valoración tiene que estar entre 1 y 5.")

    monkeypatch.setattr(web_series, "marcar", _marca)
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/leido",
                                 data={"estado": "reading", "rating": "0"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 422 and "1 y 5" in r.text


def test_filtro_leido_valido_e_invalido():
    from zascarr.web.library import _leer_filtros, _url_pagina
    filtros = _leer_filtros(1, "", "", "", "", "", "tarjetas", "", "leyendo")
    assert filtros.leido == "leyendo"
    assert "leido=leyendo" in _url_pagina(filtros, page=1)
    filtros = _leer_filtros(1, "", "", "", "", "", "tarjetas", "", "otro")
    assert filtros.leido == "" and any("lectura" in a for a in filtros.avisos)


def test_ruta_lectura_compartida_y_control_segmentado(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/lectura",
                                 data={"estado": "reading"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert 'name="estado"' in r.text
    assert "Sin leer" in r.text and "Leyendo" in r.text and "Leído" in r.text
    assert "Guardar mi lectura" not in r.text  # la fila no lleva botón


def _render_control(monkeypatch, **extra):
    from zascarr.web.routes import crear_templates
    env = crear_templates()
    from zascarr.services.lectura import TEXTOS_LECTURA
    estados = ((ReadingStatus.UNREAD, "Sin leer"), (ReadingStatus.READING, "Leyendo"),
               (ReadingStatus.COMPLETED, "Leído"))
    ctx = {"series": SimpleNamespace(id=uuid4()), "issue_id": str(uuid4()),
           "lectura": None, "textos_lectura": TEXTOS_LECTURA, "modo": "fila",
           "estados_lectura": estados, **extra}
    return env.get_template("_lectura_control.html").render(**ctx)


def _radio(html, valor):
    import re
    return re.search(rf'<input[^>]*value="{valor}"[^>]*>', html).group(0)


def test_la_ficha_de_serie_no_muestra_el_estado_de_lectura():
    """El estado (sin leer/leyendo/leído) solo se toca dentro del número."""
    plantilla = (Path(__file__).resolve().parents[1]
                 / "src/zascarr/web/templates/series_detail.html").read_text()
    assert "_lectura_control.html" not in plantilla
    assert "estados_lectura" not in plantilla
    assert "lectura-control" not in plantilla


def test_control_de_fila_pinta_el_radio_concreto_del_numero_leido():
    html = _render_control(None, lectura=_estado(ReadingStatus.READING, rating=None, nota=None))
    radio = _radio(html, "reading")
    assert "checked" in radio and "autofocus" in radio
    assert "checked" not in _radio(html, "unread")
    assert "Leyendo" in html


def test_sin_lectura_el_radio_marcado_es_sin_leer():
    html = _render_control(None, lectura=None)
    assert "checked" not in _radio(html, "reading")
    assert "checked" in _radio(html, "unread")


def test_bloque_de_numero_mantiene_rating_nota_y_boton():
    html = _render_control(None, modo="bloque")
    assert 'name="rating"' in html and 'name="nota"' in html
    assert "Guardar mi lectura" in html
    assert 'name="origen" value="numero"' in html


def test_post_de_fila_no_envia_rating_ni_nota(monkeypatch):
    _override()
    marca = AsyncMock(return_value=_estado())
    monkeypatch.setattr(web_series, "marcar", marca)
    sid, iid = uuid4(), uuid4()
    try:
        TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/lectura",
                             data={"estado": "reading"}, headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert "rating" not in marca.await_args.kwargs
    assert "nota" not in marca.await_args.kwargs


def test_bloque_303_va_a_la_ficha_del_numero(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/lectura",
                                 data={"estado": "completed", "origen": "numero"},
                                 follow_redirects=False)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 303
    assert r.headers["location"].endswith(f"/ui/series/{sid}/numero/{iid}")


def test_bloque_hx_conserva_campos(monkeypatch):
    _override()
    monkeypatch.setattr(web_series, "marcar", AsyncMock(return_value=_estado()))
    sid, iid = uuid4(), uuid4()
    try:
        r = TestClient(app).post(f"/ui/series/{sid}/numero/{iid}/lectura",
                                 data={"estado": "completed", "origen": "numero",
                                       "rating": "5", "nota": "Conservar"},
                                 headers={"HX-Request": "true"})
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert 'name="rating"' in r.text and 'name="nota"' in r.text
    assert "Guardar mi lectura" in r.text


@pytest.mark.asyncio
async def test_recuento_biblioteca_usa_el_total_no_la_pagina(monkeypatch):
    from unittest.mock import AsyncMock

    from tests.test_web_library import FakeSession
    from zascarr.web import library as lib

    class _Servicio:
        def __init__(self, _db):
            pass

        async def list_series_paginado(self, **_kwargs):
            if _kwargs.get("leido") == "si":
                return [], 3, 1
            if _kwargs.get("leido") == "leyendo":
                return [], 2, 1
            return [], 30, 1

    monkeypatch.setattr(lib, "SeriesService", _Servicio)
    monkeypatch.setattr(lib, "resolver_etiquetas", AsyncMock(return_value={}))
    filtros = lib._leer_filtros(1, "", "", "", "", "", "tarjetas", "", "si")
    ctx = await lib._contexto(FakeSession([]), filtros)
    assert ctx["recuento_lectura"] == "3 de 30 series con algún número leído."


def test_css_de_lectura_usa_variables_definidas_y_no_parte_leido():
    from pathlib import Path
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    regla = next(s for s in css.split("}") if ".lectura-estados label " in s)
    assert "var(--ink)" in regla
    assert "var(--linea)" not in regla
    assert "white-space: nowrap" in regla
    assert "--ink:" in css


@pytest.mark.asyncio
async def test_recuento_usa_etiquetas_resueltas_y_solo_series_con_issues(monkeypatch):
    from unittest.mock import AsyncMock

    from tests.test_web_library import FakeSession
    from zascarr.web import library as lib

    llamadas = []

    class _Servicio:
        def __init__(self, _db):
            pass

        async def list_series_paginado(self, **kwargs):
            llamadas.append(kwargs)
            if kwargs.get("leido") == "si":
                return [], 2, 1
            return [], 5, 1

    monkeypatch.setattr(lib, "SeriesService", _Servicio)
    monkeypatch.setattr(lib, "resolver_etiquetas", AsyncMock(return_value={}))
    filtros = lib._leer_filtros(1, "", "", "", "", "", "tarjetas", "fantasma", "si")
    ctx = await lib._contexto(FakeSession([]), filtros)
    assert ctx["recuento_lectura"] == "2 de 5 series con algún número leído."
    for kw in llamadas[-2:]:
        assert kw["etiquetas_positivas"] == ()
        assert kw["con_issues"] is True
