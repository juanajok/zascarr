"""D5 v1: construcción semanal, cruce con series seguidas y vista UI."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from zascarr.database import get_db
from zascarr.models import WishlistPolicy
from zascarr.services.novedades import (
    Semana,
    construir_semana,
    etiqueta_dia,
    etiqueta_semana,
    semana_iso,
)


def _serie(titulo, cv=None, policy=WishlistPolicy.NONE, editorial=None):
    return SimpleNamespace(id=uuid4(), title=titulo, comic_vine_id=cv,
                           wishlist_policy=policy, publisher_name=editorial)


def _item(cv, numero, fecha, volumen, vol_id, url=None):
    return {"id": cv, "issue_number": numero, "cover_date": fecha,
            "store_date": None, "site_detail_url": url,
            "volume": {"id": vol_id, "name": volumen}}


def test_construye_la_semana_y_marca_series_seguidas():
    s1 = _serie("Batman", cv=1, policy=WishlistPolicy.MISSING, editorial="DC Comics")
    s2 = _serie("Superman", cv=2)
    inicio = date(2026, 11, 16)
    semana = construir_semana(
        [_item(10, "1", "2026-11-17", "Batman", 1),
         _item(11, "2", "2026-11-18", "Superman", 2),
         _item(12, "3", "2026-11-25", "Otra", 3)],
        inicio=inicio, series=[s1, s2], wishlist_series={s2.id},
        hoy=date(2026, 11, 16))
    assert [n.cv_id for n in semana.novedades] == [10, 11]
    batman, superman = semana.novedades
    assert batman.interes and batman.editorial == "DC Comics"
    assert superman.interes and superman.editorial is None
    assert not batman.publicado and not superman.publicado
    assert semana.interesantes == 2 and semana.total == 2


def test_publicado_anunciado_y_editoriales():
    s = _serie("Batman", cv=1, editorial="DC Comics")
    inicio = date(2026, 11, 16)
    semana = construir_semana(
        [_item(1, "1", "2026-11-16", "Batman", 1),
         _item(2, "2", "2026-11-20", "Batman", 1)],
        inicio=inicio, series=[s], wishlist_series=set(), hoy=date(2026, 11, 17))
    assert [n.publicado for n in semana.novedades] == [True, False]
    assert semana.editoriales == ["DC Comics"]
    assert [d for d, _ in semana.dias] == [date(2026, 11, 16), date(2026, 11, 20)]


def test_semana_iso_acepta_fecha_y_cae_en_lunes():
    assert semana_iso("2026-11-18") == date(2026, 11, 16)
    assert semana_iso("no-es-fecha", hoy=date(2026, 11, 18)) == date(2026, 11, 16)
    assert etiqueta_dia(date(2026, 11, 16)).startswith("Lunes")
    assert "16 de noviembre" in etiqueta_semana(date(2026, 11, 16))


async def test_cargar_apagada_no_consulta(monkeypatch):
    from zascarr.services import novedades

    async def _sin_es(**kw):
        from zascarr.services.novedades_es import ResultadoES
        return ResultadoES()

    monkeypatch.setattr(novedades, "get_settings", lambda: SimpleNamespace(
        comicvine_enabled=False, comicvine_api_key="x"))
    monkeypatch.setattr(novedades, "cargar_novedades_es", _sin_es)
    with pytest.raises(novedades.NovedadesApagadaError):
        await novedades.cargar_semana(SimpleNamespace(), date(2026, 11, 16))


def test_la_pantalla_pinta_la_semana(monkeypatch):
    from zascarr.main import app
    from zascarr.web import novedades as web

    async def _cargar(db, inicio, **kw):
        s = _serie("Batman", cv=1, editorial="DC Comics")
        return construir_semana(
            [_item(1, "1", "2026-11-17", "Batman", 1, "https://cv/1")],
            inicio=inicio, series=[s], wishlist_series=set(), hoy=date(2026, 11, 16))

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/ui/novedades?semana=2026-11-18")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Batman" in r.text and "DC Comics" in r.text and "Anunciado" in r.text
    assert "Semana del 16 de noviembre" in r.text


def test_api_devuelve_json(monkeypatch):
    from zascarr.main import app
    from zascarr.web import novedades as web

    async def _cargar(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio)

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/api/novedades?semana=2026-11-18")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200 and r.json()["total"] == 0


async def test_la_fuente_pagina_hasta_el_total():
    from zascarr.services.comic_vine import ComicVineClient

    vistos = []

    class _CV(ComicVineClient):
        def __init__(self):
            pass

        async def _get(self, endpoint, params):
            vistos.append(params["offset"])
            if params["offset"] == 0:
                return {"number_of_total_results": 3,
                        "results": [{"id": 1}, {"id": 2}]}
            return {"number_of_total_results": 3,
                    "results": [{"id": 3}]}

    items = await _CV().issues_by_cover_date("2026-11-16", "2026-11-22")
    assert [i["id"] for i in items] == [1, 2, 3]
    assert vistos == [0, 2]


def test_la_pantalla_vacia_usa_el_estado_vacio(monkeypatch):
    from zascarr.main import app
    from zascarr.web import novedades as web

    async def _vacia(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio)

    monkeypatch.setattr(web, "cargar_semana", _vacia)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/ui/novedades?semana=2026-11-18")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200 and "empty-state" in r.text
    assert "No hay novedades esta semana" in r.text
    assert "filtro de editorial" not in r.text


def test_la_vista_y_la_api_no_se_cachean(monkeypatch):
    from zascarr.main import app
    from zascarr.web import novedades as web

    async def _cargar(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio)

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r_ui = TestClient(app).get("/ui/novedades")
        r_api = TestClient(app).get("/api/novedades")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r_ui.headers["cache-control"] == "no-store"
    assert r_api.headers["cache-control"] == "no-store"


def test_deduplica_la_misma_novedad():
    s = _serie("Batman", cv=1, editorial="DC")
    item = _item(1, "1", "2026-11-17", "Batman", 1)
    semana = construir_semana([item, dict(item)], inicio=date(2026, 11, 16),
                              series=[s], wishlist_series=set(),
                              hoy=date(2026, 11, 16))
    assert semana.total == 1


def test_las_editoriales_españolas_entran_en_la_misma_semana():
    s = _serie("Biblioteca Conan", cv=None, editorial="Panini")
    item = {
        "id": None, "issue_number": "", "cover_date": "2026-11-26",
        "store_date": None, "site_detail_url": "https://panini.es/x",
        "volume": {"id": None, "name": "Biblioteca Conan 24"},
        "fuente": "Panini", "editorial": "Panini Comics",
    }
    semana = construir_semana([item], inicio=date(2026, 11, 23), series=[s],
                              wishlist_series={s.id}, hoy=date(2026, 11, 16))
    n = semana.novedades[0]
    assert (n.fuente, n.editorial, n.numero, n.interes) == (
        "Panini", "Panini Comics", "", True)
    assert n.publicado is False


def test_la_pantalla_muestra_fuente_espanola_y_sin_numero(monkeypatch):
    from zascarr.main import app
    from zascarr.services.novedades import Novedad
    from zascarr.web import novedades as web

    async def _cargar(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio, novedades=[Novedad(
            cv_id=None, volumen_id=None, serie="Biblioteca Conan 24", numero="",
            fecha=inicio, publicado=False, editorial="Panini Comics",
            url="https://panini.es/x", interes=True, series_id=None,
            fuente="Panini")], fuentes_fallidas=("Norma",))

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/ui/novedades?semana=2026-11-23")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert "Panini" in r.text and "Biblioteca Conan 24" in r.text
    assert "Biblioteca Conan 24 #" not in r.text
    assert "No se pudo consultar: Norma" in r.text
    assert "Norma y Panini" in r.text and "ECC" not in r.text


async def test_encendida_sin_clave_y_sin_espanolas_no_devuelve_vacio(monkeypatch):
    from zascarr.services import novedades
    from zascarr.services.novedades_es import ResultadoES

    async def _sin_es(**kw):
        return ResultadoES()

    monkeypatch.setattr(novedades, "get_settings", lambda: SimpleNamespace(
        comicvine_enabled=True, comicvine_api_key=""))
    monkeypatch.setattr(novedades, "cargar_novedades_es", _sin_es)
    with pytest.raises(novedades.NovedadesApagadaError):
        await novedades.cargar_semana(SimpleNamespace(), date(2026, 11, 16))


def test_api_expone_las_fuentes_que_faltan(monkeypatch):
    from zascarr.main import app
    from zascarr.web import novedades as web

    async def _cargar(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio, fuentes_fallidas=("Norma",))

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/api/novedades?semana=2026-11-18")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert r.json()["fuentes_fallidas"] == ["Norma"]


def test_el_prefijo_solo_casa_si_lo_que_sigue_es_numero_o_edicion():
    s = _serie("Batman", cv=None)
    inicio = date(2026, 11, 23)
    def _item(titulo):
        return {"id": None, "issue_number": "", "cover_date": "2026-11-26",
                "site_detail_url": None, "volume": {"id": None, "name": titulo},
                "fuente": "Panini", "editorial": "Panini Comics"}
    semana = construir_semana([_item("Batman Beyond 1"), _item("Batman Universe"),
                               _item("Batman 24")],
                              inicio=inicio, series=[s], wishlist_series={s.id},
                              hoy=date(2026, 11, 16))
    por_titulo = {n.serie: n.interes for n in semana.novedades}
    assert por_titulo == {"Batman Beyond 1": False, "Batman Universe": False,
                          "Batman 24": True}


def test_el_matching_real_de_norma_y_panini_no_cruza_vecinos():
    series = [_serie("Batman", cv=None), _serie("Blade Runner 2019", cv=None),
              _serie("El Depravado", cv=None), _serie("Cyberpunk 2077", cv=None),
              _serie("Biblioteca Conan", cv=None)]
    inicio = date(2026, 11, 23)
    def _item(titulo):
        return {"id": None, "issue_number": "", "cover_date": "2026-11-26",
                "site_detail_url": None, "volume": {"id": None, "name": titulo},
                "fuente": "Norma", "editorial": "Norma Editorial"}
    titulos = ["Batman", "Batman 24", "Batman Beyond 1", "Batman Universe",
               "Blade Runner 2019 [Ed. Integral]", "El Depravado [Ed. de lujo]",
               "Cyberpunk 2077. Chrome",
               "Biblioteca Conan. Conan el Bárbaro. 24"]
    semana = construir_semana([_item(t) for t in titulos], inicio=inicio,
                              series=series, wishlist_series={f.id for f in series},
                              hoy=date(2026, 11, 16))
    interesa = {n.serie: n.interes for n in semana.novedades}
    assert interesa["Batman 24"] and interesa["Batman"]
    assert not interesa["Batman Beyond 1"] and not interesa["Batman Universe"]
    assert interesa["Blade Runner 2019 [Ed. Integral]"]
    assert interesa["El Depravado [Ed. de lujo]"]
    assert interesa["Cyberpunk 2077. Chrome"]
    assert interesa["Biblioteca Conan. Conan el Bárbaro. 24"]


def test_las_tarjetas_usan_portada_local_y_marcador_si_no_hay_serie(monkeypatch):
    from uuid import uuid4

    from zascarr.main import app
    from zascarr.services.novedades import Novedad
    from zascarr.web import novedades as web

    sid = uuid4()

    async def _cargar(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio, novedades=[
            Novedad(cv_id=None, volumen_id=None, serie="Con portada", numero="1",
                    fecha=inicio, publicado=False, editorial="Norma Editorial",
                    url=None, interes=True, series_id=sid, fuente="Norma",
                    tiene_portada=True),
            Novedad(cv_id=None, volumen_id=None, serie="Sin portada", numero="",
                    fecha=inicio, publicado=False, editorial="Panini Comics",
                    url=None, interes=False, series_id=None, fuente="Panini"),
        ])

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/ui/novedades?semana=2026-11-23")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert r.status_code == 200
    assert f"/ui/series/{sid}/portada?v=2" in r.text
    assert r.text.count('class="portada ') >= 2
    assert 'class="portada-carga' not in r.text
    assert "Sin portada" in r.text


def test_si_la_serie_casa_pero_no_tiene_portada_no_se_pide_la_imagen(monkeypatch):
    from uuid import uuid4

    from zascarr.main import app
    from zascarr.services.novedades import Novedad
    from zascarr.web import novedades as web

    sid = uuid4()

    async def _cargar(db, inicio, **kw):
        return Semana(inicio=inicio, fin=inicio, novedades=[Novedad(
            cv_id=None, volumen_id=None, serie="Serie sin imagen", numero="1",
            fecha=inicio, publicado=False, editorial="Norma Editorial", url=None,
            interes=True, series_id=sid, fuente="Norma", tiene_portada=False)])

    monkeypatch.setattr(web, "cargar_semana", _cargar)
    app.dependency_overrides[get_db] = lambda: object()
    try:
        r = TestClient(app).get("/ui/novedades?semana=2026-11-23")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert f"/ui/series/{sid}/portada" not in r.text
    assert 'class="portada ' in r.text  # marcador de ZascArr


def test_la_rejilla_no_pasa_de_tres_columnas():
    from pathlib import Path
    import re
    css = Path("src/zascarr/static/web.css").read_text(encoding="utf-8")
    # Solo la rejilla de Novedades: otras pantallas pueden tener su propio reparto (las cifras del
    # Inicio van en una fila de cuatro entre 860 y 1100 px, plantilla P1).
    columnas = re.findall(r"\.novedades-dia \{[^}]*grid-template-columns: repeat\((\d+)", css)
    assert columnas and max(int(n) for n in columnas) == 3
    assert ".novedad-portada a:focus-visible" in css
