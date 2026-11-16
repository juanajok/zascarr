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

    monkeypatch.setattr(novedades, "get_settings", lambda: SimpleNamespace(
        comicvine_enabled=False, comicvine_api_key="x"))
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
