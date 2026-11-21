"""UXA-08b (#1205): variante «b» de la barra inferior del móvil, detrás de `NAV_MOVIL_VARIANTE`.

Por defecto no cambia nada («a»). «b» pone Biblioteca en la barra y Estado dentro de «Más», con un
punto de aviso sobre «Más» (el `cnt-estado` sigue en la barra lateral del escritorio).
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from zascarr.config import Settings, get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.web.menu import ENTRADAS, entradas_para, mas_tiene_aviso
from zascarr.web.routes import crear_templates


def _principales(variante):
    return [e.clave for e in entradas_para(variante) if e.movil_principal]


def test_por_defecto_es_la_variante_a_y_no_cambia_nada():
    assert Settings.model_fields["nav_movil_variante"].default == "a"
    assert entradas_para("a") is ENTRADAS
    assert entradas_para("desconocida") is ENTRADAS
    assert _principales("a") == ["inicio", "revisar", "deseados", "estado"]
    assert mas_tiene_aviso("a") is False


def test_la_variante_b_pone_biblioteca_en_la_barra_y_estado_en_mas():
    assert _principales("b") == ["inicio", "revisar", "biblioteca", "deseados"]
    estado = next(e for e in entradas_para("b") if e.clave == "estado")
    assert estado.movil_principal is False and estado.contador == "estado"
    assert mas_tiene_aviso("b") is True
    # La barra sigue teniendo cuatro entradas y las URL no cambian.
    assert len(_principales("b")) == 4
    assert {e.clave: e.url for e in entradas_para("b")} == {e.clave: e.url for e in ENTRADAS}


def test_el_valor_de_la_configuracion_solo_admite_a_o_b(monkeypatch):
    monkeypatch.setenv("NAV_MOVIL_VARIANTE", "c")
    get_settings.cache_clear()
    try:
        with pytest.raises(Exception):  # noqa: B017, PT011 — pydantic ValidationError
            get_settings()
    finally:
        monkeypatch.delenv("NAV_MOVIL_VARIANTE")
        get_settings.cache_clear()


def _menu(monkeypatch, variante, ruta="/ui/"):
    monkeypatch.setenv("NAV_MOVIL_VARIANTE", variante)
    get_settings.cache_clear()
    try:
        env = crear_templates().env
        return env.from_string("{{ ui.menu(ruta) }}").render(ruta=ruta)
    finally:
        monkeypatch.delenv("NAV_MOVIL_VARIANTE")
        get_settings.cache_clear()


def _ids(html):
    return re.findall(r'id="([^"]+)"', html)


@pytest.mark.parametrize("variante", ["a", "b"])
def test_ningun_id_se_repite_en_el_menu(monkeypatch, variante):
    ids = _ids(_menu(monkeypatch, variante))
    assert len(ids) == len(set(ids)), ids


def test_variante_a_no_tiene_marcador_de_mas(monkeypatch):
    html = _menu(monkeypatch, "a")
    assert 'id="cnt-mas"' not in html
    assert html.count('id="cnt-estado"') == 1


def test_variante_b_lleva_el_punto_en_mas_y_estado_sin_contador_en_el_panel(monkeypatch):
    html = _menu(monkeypatch, "b")
    assert html.count('id="cnt-mas"') == 1
    assert html.count('id="cnt-estado"') == 1  # la barra/lateral; no el panel
    panel = html[html.index('class="nav-mas-panel"'):]
    assert 'href="/estado"' in panel and 'id="cnt-estado"' not in panel
    # El punto de «Más» está dentro de su resumen, que es donde se posiciona.
    resumen = html[html.index("<summary"):html.index("</summary>")]
    assert 'id="cnt-mas"' in resumen
    barra = html[:html.index('class="nav-mas')]
    assert barra.count('href="/ui/biblioteca"') == 1 and 'class="nav-enlace"' in barra


def test_en_la_variante_b_estado_activo_marca_mas(monkeypatch):
    html = _menu(monkeypatch, "b", "/estado")
    assert "nav-mas-activa" in html


class _Sesion:
    async def execute(self, *a, **k):
        raise AssertionError


@pytest.mark.parametrize("variante, esperado", [("a", False), ("b", True)])
def test_el_fragmento_de_contadores_solo_toca_mas_en_la_variante_b(
        monkeypatch, variante, esperado):
    from zascarr.web import navegacion

    async def datos():
        from types import SimpleNamespace
        return SimpleNamespace(pendientes=0, deseados=0), True

    monkeypatch.setattr(navegacion, "_datos", datos)
    navegacion._calculo_en_curso = None
    monkeypatch.setenv("NAV_MOVIL_VARIANTE", variante)
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: _Sesion()
    try:
        r = TestClient(app).get("/ui/_nav/estado")
    finally:
        app.dependency_overrides.pop(get_db, None)
        monkeypatch.delenv("NAV_MOVIL_VARIANTE")
        get_settings.cache_clear()
        navegacion._calculo_en_curso = None
    assert r.status_code == 200
    assert ('id="cnt-mas"' in r.text) is esperado
    assert 'id="cnt-estado"' in r.text
