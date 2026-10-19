"""#239 / ADR 0013 — fuentes de metadatos apagadas por defecto y aviso en Ajustes (sin Postgres)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zascarr.config import Settings, get_settings
from zascarr.main import app

CAMPOS = ("comicvine_enabled", "anilist_enabled", "tebeosfera_enabled", "gcd_enabled")


@pytest.fixture
def restaurar():
    s = get_settings()
    antes = {c: getattr(s, c) for c in CAMPOS}
    yield s
    for c, v in antes.items():
        setattr(s, c, v)


class TestDefaults:

    @pytest.mark.parametrize("campo", CAMPOS)
    def test_los_cuatro_interruptores_nacen_apagados(self, campo):
        """Mecanismo del cambio: el default de `config.py`, sin `.env` ni override, es `False`."""
        assert getattr(Settings(_env_file=None), campo) is False

    @pytest.mark.parametrize("campo", CAMPOS)
    def test_el_env_no_los_gobierna_y_el_default_es_el_de_codigo(self, campo, monkeypatch):
        """Compose solo transmite FORUM_ENABLED; si alguien exporta la variable, pydantic la lee (vía de pruebas), pero el default de código es el apagado."""
        monkeypatch.delenv(campo.upper(), raising=False)
        assert getattr(Settings(_env_file=None), campo) is False

    def test_prowlarr_transmission_amule_y_foro_siguen_apagados(self):
        s = Settings(_env_file=None)
        assert (s.prowlarr_enabled, s.transmission_enabled, s.amule_enabled) == (False, False, False)


class TestAvisoDeAjustes:

    @pytest.mark.parametrize("campo", CAMPOS)
    def test_con_cualquiera_de_las_cuatro_activa_avisa_de_que_consulta_internet(self, restaurar, campo):
        for c in CAMPOS:
            setattr(restaurar, c, c == campo)
        r = TestClient(app).get("/ui/ajustes")
        assert r.status_code == 200
        assert 'id="aviso-fuentes-activas"' in r.text and "Consultan Internet" in r.text
        assert 'id="aviso-fuentes-apagadas"' not in r.text

    def test_con_todas_apagadas_lo_dice_y_no_alarma(self, restaurar):
        for c in CAMPOS:
            setattr(restaurar, c, False)
        r = TestClient(app).get("/ui/ajustes")
        assert 'id="aviso-fuentes-apagadas"' in r.text and "no consulta Internet" in r.text
        assert 'id="aviso-fuentes-activas"' not in r.text

    def test_el_contrato_del_formulario_de_fuentes_no_cambia(self, restaurar):
        r = TestClient(app).get("/ui/ajustes")
        assert 'hx-post="/ui/ajustes/guardar/fuentes"' in r.text and 'hx-target="#resultado-fuentes"' in r.text
        for c in CAMPOS:
            assert f'name="{c}"' in r.text
