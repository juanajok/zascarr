"""Cadencia de «Actualizar la biblioteca» en Ajustes (#1160)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from tests.test_web_ajustes import FakeSession, _override_get_db, restaurar_settings  # noqa: F401
from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.main import app
from zascarr.services.runtime_settings import _ALL_FIELDS, OVERRIDABLE_FIELDS


def _guardar(valor, **extra):
    app.dependency_overrides[get_db] = _override_get_db(FakeSession())
    try:
        return TestClient(app).post(
            "/ui/ajustes/guardar/actualizar-biblioteca",
            data={"rescan_interval_minutes": valor, **extra})
    finally:
        app.dependency_overrides.pop(get_db, None)


def _pagina():
    app.dependency_overrides[get_db] = _override_get_db(FakeSession())
    try:
        return TestClient(app).get("/ui/ajustes")
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_la_cadencia_es_un_campo_que_ajustes_puede_tocar():
    assert "rescan_interval_minutes" in OVERRIDABLE_FIELDS["actualizar_biblioteca"]
    assert "rescan_interval_minutes" in _ALL_FIELDS


@pytest.mark.parametrize("valor,esperado", [("0", 0), ("1440", 1440), ("10080", 10080)])
def test_guarda_y_aplica_al_instante_sin_reiniciar(restaurar_settings, valor, esperado):  # noqa: F811
    r = _guardar(valor)
    assert r.status_code == 200
    assert get_settings().rescan_interval_minutes == esperado


def test_apagada_dice_que_se_puede_hacer_desde_biblioteca(restaurar_settings):  # noqa: F811
    r = _guardar("0")
    assert "Ya no se actualiza sola" in r.text and "Biblioteca" in r.text


def test_diaria_dice_cuando_sera_la_proxima(restaurar_settings):  # noqa: F811
    assert "Guardado. La próxima será " in _guardar("1440").text


def test_un_numero_cualquiera_no_se_admite(restaurar_settings):  # noqa: F811
    get_settings().rescan_interval_minutes = 1440
    _guardar("37")
    assert get_settings().rescan_interval_minutes == 1440
    _guardar("no-es-un-numero")
    assert get_settings().rescan_interval_minutes == 1440


def test_el_valor_fijado_por_la_instalacion_se_conserva_al_guardar(restaurar_settings):  # noqa: F811
    """720 viene del `.env`: se ofrece como cuarta opción y guardarla no lo pisa en silencio."""
    get_settings().rescan_interval_minutes = 720
    html = _pagina().text
    assert "Cada 12 horas (fijado en la instalación)" in html
    _guardar("720")
    assert get_settings().rescan_interval_minutes == 720


def test_con_un_valor_estandar_no_aparece_la_opcion_extra(restaurar_settings):  # noqa: F811
    get_settings().rescan_interval_minutes = 1440
    html = _pagina().text
    assert "fijado en la instalación" not in html
    assert "Una vez a la semana" in html and "Desactivado" in html


def test_la_tarjeta_va_en_tu_zascarr_con_el_ancla_que_enlaza_biblioteca(restaurar_settings):  # noqa: F811
    html = _pagina().text
    assert 'id="actualizar-biblioteca"' in html
    orden = [html.index(a) for a in
             ('id="ajustes-propio"', 'id="actualizar-biblioteca"', 'id="discos-biblioteca"')]
    assert orden == sorted(orden)
    assert "Actualizar sola" in html
    tarjeta = html.split('id="actualizar-biblioteca"', 1)[1].split("</fieldset>", 1)[0]
    visible = re.sub(r"<[^>]+>", " ", tarjeta).lower()   # solo el texto: el `name` es interno
    for prohibida in ("rescan", "reescan", "catálogo"):
        assert prohibida not in visible
