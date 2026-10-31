"""#123 (SecOps H-2): los umbrales de disco tienen cota superior y `warn >= error`; si se invierten, `/api/health` sería incoherente."""
from __future__ import annotations

import pytest
import structlog.testing
from pydantic import ValidationError

from zascarr.config import Settings

MAXIMO_MB = 10 * 1024 * 1024        # 10 TiB: más que cualquier disco de una Raspberry Pi


def _ajustes(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_los_valores_por_defecto_son_validos():
    s = _ajustes()
    assert s.disk_warn_free_mb >= s.disk_error_free_mb


def test_aviso_igual_a_error_no_cambia_nada_ni_avisa():
    with structlog.testing.capture_logs() as registro:
        s = _ajustes(disk_warn_free_mb=512, disk_error_free_mb=512)
    assert (s.disk_warn_free_mb, s.disk_error_free_mb) == (512, 512)
    assert not [e for e in registro if e["event"] == "config.umbrales_de_disco_invertidos"]


def test_un_par_valido_no_cambia_ni_avisa():
    with structlog.testing.capture_logs() as registro:
        s = _ajustes(disk_warn_free_mb=4096, disk_error_free_mb=1024)
    assert (s.disk_warn_free_mb, s.disk_error_free_mb) == (4096, 1024)
    assert registro == []


def test_un_par_invertido_arranca_ajusta_el_error_al_aviso_y_deja_un_aviso_en_el_registro():
    """O-1 (decisión del PO): lo observacional no bloquea el arranque (CLAUDE.md §3.2)."""
    with structlog.testing.capture_logs() as registro:
        s = _ajustes(disk_warn_free_mb=100, disk_error_free_mb=512)
    assert (s.disk_warn_free_mb, s.disk_error_free_mb) == (100, 100)           # error = min(error, warn)
    avisos = [e for e in registro if e["event"] == "config.umbrales_de_disco_invertidos"]
    assert len(avisos) == 1 and avisos[0]["log_level"] == "warning"
    assert avisos[0]["DISK_WARN_FREE_MB"] == 100 and avisos[0]["DISK_ERROR_FREE_MB"] == 512
    assert set(avisos[0]) <= {"event", "log_level", "DISK_WARN_FREE_MB", "DISK_ERROR_FREE_MB", "ajustado_a"}


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


def test_tambien_se_corrige_desde_el_entorno_sin_volcar_valores_del_env(monkeypatch):
    monkeypatch.setenv("DISK_WARN_FREE_MB", "10")
    monkeypatch.setenv("DISK_ERROR_FREE_MB", "500")
    monkeypatch.setenv("SECRET_KEY", "no-debe-salir-en-el-registro")
    with structlog.testing.capture_logs() as registro:
        s = Settings(_env_file=None)
    assert (s.disk_warn_free_mb, s.disk_error_free_mb) == (10, 10)
    assert "no-debe-salir-en-el-registro" not in str(registro)
