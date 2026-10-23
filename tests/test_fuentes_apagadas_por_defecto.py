# ruff: noqa: E501
"""#239 / ADR 0013 — fuentes de metadatos apagadas por defecto y aviso en Ajustes (sin Postgres)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zascarr.config import Settings, get_settings
from zascarr.main import app

CAMPOS = ("comicvine_enabled", "anilist_enabled", "tebeosfera_enabled", "gcd_enabled")


@pytest.fixture
def restaurar():
    """Restaura TODOS los campos que `save()`/`apply_overrides` pueden mutar en el Settings compartido (si no, una prueba que
    guarda una tarjeta de Ajustes contamina a las siguientes: p. ej. dejaba una clave de Comic Vine puesta)."""
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    antes = {c: getattr(s, c) for c in _ALL_FIELDS}
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
    """El aviso es SOLO del estado heredado (persistido), no de «hay fuentes activas»."""

    def test_en_estado_heredado_avisa_y_dice_como_decidir(self, restaurar):
        for c in CAMPOS:
            setattr(restaurar, c, True)
        restaurar.fuentes_heredadas = True
        r = TestClient(app).get("/ui/ajustes")
        assert r.status_code == 200
        assert 'id="aviso-fuentes-heredadas"' in r.text and "por compatibilidad con tu instalación anterior" in r.text
        assert "Guardar" in r.text

    @pytest.mark.parametrize("campo", CAMPOS)
    def test_con_fuentes_activas_pero_decision_explicita_no_hay_aviso(self, restaurar, campo):
        for c in CAMPOS:
            setattr(restaurar, c, c == campo)
        restaurar.fuentes_heredadas = False
        r = TestClient(app).get("/ui/ajustes")
        assert 'id="aviso-fuentes-heredadas"' not in r.text

    def test_instalacion_nueva_sin_fuentes_no_avisa(self, restaurar):
        for c in CAMPOS:
            setattr(restaurar, c, False)
        restaurar.fuentes_heredadas = False
        assert 'id="aviso-fuentes-heredadas"' not in TestClient(app).get("/ui/ajustes").text

    def test_el_contrato_del_formulario_de_fuentes_no_cambia(self, restaurar):
        r = TestClient(app).get("/ui/ajustes")
        assert 'hx-post="/ui/ajustes/guardar/fuentes"' in r.text and 'hx-target="#resultado-fuentes"' in r.text
        for c in CAMPOS:
            assert f'name="{c}"' in r.text


class TestElMarcadorSePersisteYSeLimpiaAlGuardar:

    def _cliente(self, valores: dict):
        from unittest.mock import MagicMock

        from zascarr.database import get_db

        fila = MagicMock(values=dict(valores))

        class Sesion:
            async def execute(self, _s):
                r = MagicMock()
                r.scalar_one_or_none = MagicMock(return_value=fila)
                return r

            def add(self, o):
                pass

            async def flush(self):
                return None

        async def _db():
            yield Sesion()

        app.dependency_overrides[get_db] = _db
        return TestClient(app), fila

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_guardar_fuentes_pone_el_marcador_a_false_aunque_no_cambie_nada(self, restaurar):
        restaurar.fuentes_heredadas = True
        cliente, fila = self._cliente({"comicvine_enabled": True, "fuentes_heredadas": True})
        r = cliente.post("/ui/ajustes/guardar/fuentes", data={"comicvine_enabled": "true"})
        assert r.status_code == 200, r.text
        assert fila.values["fuentes_heredadas"] is False and fila.values["comicvine_enabled"] is True
        assert restaurar.fuentes_heredadas is False
        assert 'id="aviso-fuentes-heredadas"' not in TestClient(app).get("/ui/ajustes").text

    def test_guardar_otra_tarjeta_no_quita_el_aviso_de_fuentes(self, restaurar):
        restaurar.fuentes_heredadas = True
        cliente, fila = self._cliente({"fuentes_heredadas": True})
        r = cliente.post("/ui/ajustes/guardar/comic-vine", data={"comicvine_api_key": "k"})
        assert r.status_code == 200, r.text
        assert fila.values["fuentes_heredadas"] is True and restaurar.fuentes_heredadas is True

    def test_tras_un_reinicio_el_marcador_guardado_se_aplica_a_la_configuracion(self, restaurar):
        """`load_overrides_at_startup` aplica lo persistido: el estado no se deduce en cada arranque."""
        from zascarr.services.runtime_settings import apply_overrides

        restaurar.fuentes_heredadas = False
        apply_overrides({"fuentes_heredadas": True, "comicvine_enabled": True})
        assert restaurar.fuentes_heredadas is True and restaurar.comicvine_enabled is True
