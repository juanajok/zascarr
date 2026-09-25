"""
tests/test_runtime_settings.py

Suite de RuntimeSettingsService (D11): ajustes de integraciones editables
desde /ui/ajustes. El punto delicado es que apply_overrides() muta el
Settings real cacheado por get_settings() — cada test que lo ejercita
restaura los atributos que tocó, para no filtrar estado a otros tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from zascarr.config import get_settings
from zascarr.services.runtime_settings import RuntimeSettingsService, apply_overrides


class FakeSession:
    def __init__(self, existing_values: dict | None = None):
        self._row = MagicMock(values=dict(existing_values) if existing_values is not None else None)
        self.added: list = []

    async def execute(self, _statement):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=self._row if self._row.values is not None else None)
        return result

    def add(self, obj):
        self.added.append(obj)
        self._row = obj

    async def flush(self):
        return None


@pytest.fixture
def restaurar_settings():
    """Los tests que llaman a save()/apply_overrides() mutan el Settings
    real (get_settings() está @lru_cache, es el mismo objeto siempre).
    Se restauran los campos overridables al valor de antes del test."""
    from zascarr.services.runtime_settings import _ALL_FIELDS
    s = get_settings()
    originales = {campo: getattr(s, campo) for campo in _ALL_FIELDS}
    yield
    for campo, valor in originales.items():
        setattr(s, campo, valor)


class TestGetOverrides:

    @pytest.mark.asyncio
    async def test_sin_fila_previa_devuelve_vacio_y_la_crea(self):
        session = FakeSession(existing_values=None)
        service = RuntimeSettingsService(db=session)

        overrides = await service.get_overrides()

        assert overrides == {}
        assert session.added  # la fila se creó de forma perezosa

    @pytest.mark.asyncio
    async def test_devuelve_los_valores_ya_guardados(self):
        session = FakeSession(existing_values={"prowlarr_url": "http://x:9696"})
        service = RuntimeSettingsService(db=session)

        overrides = await service.get_overrides()

        assert overrides == {"prowlarr_url": "http://x:9696"}


class TestSave:

    @pytest.mark.asyncio
    async def test_clave_desconocida_lanza_value_error(self):
        service = RuntimeSettingsService(db=FakeSession(existing_values={}))
        with pytest.raises(ValueError, match="desconocido"):
            await service.save({"db_pool_size": 99})

    @pytest.mark.asyncio
    async def test_secreto_vacio_no_pisa_el_ya_guardado(self, restaurar_settings):
        session = FakeSession(existing_values={"comicvine_api_key": "clave-real"})
        service = RuntimeSettingsService(db=session)

        await service.save({"comicvine_api_key": ""})

        assert session._row.values["comicvine_api_key"] == "clave-real"

    @pytest.mark.asyncio
    async def test_guarda_y_aplica_al_instante(self, restaurar_settings):
        session = FakeSession(existing_values={})
        service = RuntimeSettingsService(db=session)

        await service.save({"prowlarr_url": "http://prowlarr-nuevo:9696", "prowlarr_enabled": True})

        assert session._row.values["prowlarr_url"] == "http://prowlarr-nuevo:9696"
        # El propio Settings cacheado ya refleja el cambio, sin reiniciar:
        assert get_settings().prowlarr_url == "http://prowlarr-nuevo:9696"
        assert get_settings().prowlarr_enabled is True


class TestApplyOverrides:

    def test_ignora_claves_que_no_son_overridables(self, restaurar_settings):
        valor_previo = get_settings().log_level
        apply_overrides({"log_level": "DEBUG"})
        assert get_settings().log_level == valor_previo
