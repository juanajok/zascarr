"""#123 (SecOps H-2): los umbrales de disco tienen cota superior y `warn >= error`; si se invierten, `/api/health` sería incoherente."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from zascarr.config import Settings

MAXIMO_MB = 10 * 1024 * 1024        # 10 TiB: más que cualquier disco de una Raspberry Pi


def _ajustes(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_los_valores_por_defecto_son_validos():
    s = _ajustes()
    assert s.disk_warn_free_mb >= s.disk_error_free_mb


def test_aviso_igual_a_error_es_valido():
    s = _ajustes(disk_warn_free_mb=512, disk_error_free_mb=512)
    assert (s.disk_warn_free_mb, s.disk_error_free_mb) == (512, 512)


def test_aviso_menor_que_error_se_rechaza_con_un_mensaje_claro():
    with pytest.raises(ValidationError) as e:
        _ajustes(disk_warn_free_mb=100, disk_error_free_mb=512)
    assert "DISK_WARN_FREE_MB" in str(e.value) and "DISK_ERROR_FREE_MB" in str(e.value)


@pytest.mark.parametrize("campo", ["disk_warn_free_mb", "disk_error_free_mb"])
def test_el_maximo_pasa_y_uno_mas_se_rechaza(campo):
    # warn >= error: para llevar `error` al máximo, `warn` también va al máximo
    otros = {"disk_error_free_mb": 0} if campo == "disk_warn_free_mb" else {"disk_warn_free_mb": MAXIMO_MB}
    assert getattr(_ajustes(**{campo: MAXIMO_MB, **otros}), campo) == MAXIMO_MB
    with pytest.raises(ValidationError):
        _ajustes(**{campo: MAXIMO_MB + 1, **otros})


@pytest.mark.parametrize("campo", ["disk_warn_free_mb", "disk_error_free_mb"])
def test_un_negativo_se_sigue_rechazando(campo):
    with pytest.raises(ValidationError):
        _ajustes(**{campo: -1})


def test_tambien_se_valida_desde_el_entorno(monkeypatch):
    monkeypatch.setenv("DISK_WARN_FREE_MB", "10")
    monkeypatch.setenv("DISK_ERROR_FREE_MB", "500")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
