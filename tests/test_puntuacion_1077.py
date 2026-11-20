"""#1077: filtro/orden por puntuación (normalización y plantilla)."""
from __future__ import annotations

from pathlib import Path

from zascarr.web.library import Filtros, _leer_filtros, _qs


def _leer(**kw):
    return _leer_filtros(page="1", q=kw.pop("q", ""), tradition="",
                         publisher_id="", character_id="", story_arc_id="",
                         vista="", etiquetas="", leido="",
                         orden=kw.pop("orden", ""), **kw)


def test_puntuacion_normaliza_y_url():
    for valor in ("con", "sin", "4-5"):
        f = _leer(puntuacion=valor)
        assert f.puntuacion == valor
        assert f"puntuacion={valor}" in _qs(f, page=1)
    malo = _leer(puntuacion="alta")
    assert malo.puntuacion == "" and any("puntuaci" in a for a in malo.avisos)
    assert "puntuacion" not in _qs(Filtros(), page=1)


def test_orden_valoracion_y_plantilla():
    f = _leer(orden="valoracion")
    assert f.orden == "valoracion"
    assert "orden=valoracion" in _qs(f, page=1)
    panel = Path("src/zascarr/web/templates/_filtros_panel_campos.html").read_text()
    assert 'id="f-puntuacion"' in panel and "Con valoración" in panel and "Sin valorar" in panel
    assert "4–5" in panel


def test_ssr_y_fragmento_con_puntuacion():
    from tests.test_web_library import FakeExecResult, FakeSession, make_series, use_fake_session

    with use_fake_session(FakeSession([
            FakeExecResult([]), FakeExecResult(1), FakeExecResult([make_series()])])) as client:
        r = client.get("/ui/biblioteca?puntuacion=4-5&orden=valoracion")
    assert r.status_code == 200
    assert 'id="f-puntuacion"' in r.text
    assert "Puntuación 4–5" in r.text
    assert 'value="valoracion" selected' in r.text
    with use_fake_session(FakeSession([
            FakeExecResult(1), FakeExecResult([make_series()])])) as client:
        f = client.get("/ui/biblioteca/resultados?puntuacion=con&orden=valoracion",
                       headers={"HX-Request": "true"})
    assert f.status_code == 200
    assert "puntuacion=con" in f.headers["HX-Push-Url"]
    assert "orden=valoracion" in f.headers["HX-Push-Url"]


def test_puntuacion_cuenta_como_filtro_y_select_cabe():
    css = Path("src/zascarr/static/web.css").read_text()
    assert "filtros_finales.puntuacion" in Path("src/zascarr/web/library.py").read_text()
    assert '("valoracion", "Valoración")' in Path("src/zascarr/web/library.py").read_text()
    assert "max-width: 11rem" in css and "max-width: 9rem" in css
