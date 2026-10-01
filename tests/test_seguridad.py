"""
tests/test_seguridad.py

`services/seguridad.py` (A11): la regla de contraseña y su guardado, compartidos
por Ajustes y por el instalador (`python -m zascarr.cli.seguridad`). El router de
Ajustes ya tiene sus pruebas HTTP (`test_web_ajustes.py`); aquí se fija el
contrato del servicio, que es lo que garantiza que las dos entradas den el mismo
veredicto.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zascarr.services import seguridad
from zascarr.services.seguridad import (
    LONGITUD_MINIMA,
    LONGITUD_RECOMENDADA,
    fijar_seguridad,
    url_publica_valida,
    validar_contrasena,
)


class TestValidarContrasena:
    """Los tres tramos de la regla: rechazo, aviso y aceptación limpia."""

    def test_por_debajo_del_minimo_se_rechaza(self):
        error, aviso = validar_contrasena("x" * (LONGITUD_MINIMA - 1))
        assert error is not None and aviso is None
        assert str(LONGITUD_MINIMA) in error

    def test_el_minimo_exacto_se_acepta_con_aviso(self):
        error, aviso = validar_contrasena("x" * LONGITUD_MINIMA)
        assert error is None and aviso is not None

    def test_entre_el_minimo_y_el_recomendado_avisa(self):
        error, aviso = validar_contrasena("x" * (LONGITUD_RECOMENDADA - 1))
        assert error is None and aviso is not None

    def test_la_longitud_recomendada_no_avisa(self):
        assert validar_contrasena("x" * LONGITUD_RECOMENDADA) == (None, None)

    def test_vacia_significa_no_cambiar_y_no_se_valida(self):
        assert validar_contrasena("") == (None, None)

    def test_se_mide_en_caracteres_no_en_bytes(self):
        """Una contraseña con tildes/ñ no se penaliza por ocupar más bytes."""
        assert validar_contrasena("ñ" * LONGITUD_MINIMA)[0] is None


class TestUrlPublicaValida:
    """La URL pública de un proxy inverso con TLS: solo `https://` con host."""

    @pytest.mark.parametrize("url", [
        "https://tebeos.ejemplo.org",
        "https://tebeos.ejemplo.org:8443",
        "https://ejemplo.org/zascarr",
        "https://192.168.1.50",
    ])
    def test_acepta(self, url):
        assert url_publica_valida(url)

    @pytest.mark.parametrize("url", [
        "", "tebeos.ejemplo.org", "http://tebeos.ejemplo.org",
        "https://", "https:///ruta", "ftp://ejemplo.org", "javascript:alert(1)",
        "https://[::1", "  ",
    ])
    def test_rechaza(self, url):
        assert not url_publica_valida(url)


@pytest.fixture
def ajustes(monkeypatch):
    """Settings actuales + un `save` que recoge lo que se guardaría."""
    actuales = MagicMock(
        auth_mode="none", auth_username="", auth_password_hash="", auth_session_version=3,
    )
    monkeypatch.setattr(seguridad, "get_settings", lambda: actuales)
    guardado: list[dict] = []

    async def _save(self, cambios):
        guardado.append(cambios)

    monkeypatch.setattr(seguridad.RuntimeSettingsService, "save", _save)
    limpiar = MagicMock()
    monkeypatch.setattr(seguridad, "limpiar_cache_basic", limpiar)
    monkeypatch.setattr(seguridad, "hash_password_async", AsyncMock(return_value="HASH"))
    return actuales, guardado, limpiar


class TestFijarSeguridad:

    @pytest.mark.asyncio
    async def test_activar_password_sin_ninguna_se_rechaza(self, ajustes):
        _, guardado, _ = ajustes
        r = await fijar_seguridad(MagicMock(), modo="password", usuario="", password="", base_url="")
        assert r.error == seguridad.MENSAJE_SIN_CONTRASENA
        assert guardado == []

    @pytest.mark.asyncio
    async def test_activar_password_con_una_ya_guardada_no_exige_reescribirla(self, ajustes):
        actuales, guardado, _ = ajustes
        actuales.auth_password_hash = "pbkdf2…"
        r = await fijar_seguridad(MagicMock(), modo="password", usuario="", password="", base_url="")
        assert r.error is None
        assert "auth_password_hash" not in guardado[0]

    @pytest.mark.asyncio
    async def test_user_password_sin_usuario_se_rechaza(self, ajustes):
        r = await fijar_seguridad(
            MagicMock(), modo="user_password", usuario="", password="x" * 15, base_url="")
        assert r.error == seguridad.MENSAJE_SIN_USUARIO

    @pytest.mark.asyncio
    async def test_contrasena_corta_se_rechaza_y_no_guarda_nada(self, ajustes):
        _, guardado, _ = ajustes
        r = await fijar_seguridad(MagicMock(), modo="password", usuario="", password="corta", base_url="")
        assert r.error == seguridad.MENSAJE_CORTA
        assert guardado == []

    @pytest.mark.asyncio
    async def test_guardar_una_contrasena_nueva_hashea_sube_version_y_limpia_la_cache(self, ajustes):
        _, guardado, limpiar = ajustes
        r = await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="x" * 15, base_url="")
        assert r.error is None and r.aviso is None and r.cambia_credenciales
        assert guardado[0]["auth_password_hash"] == "HASH"   # nunca la contraseña en claro
        assert guardado[0]["auth_session_version"] == 4
        assert "x" * 15 not in str(guardado[0])
        limpiar.assert_called_once()

    @pytest.mark.asyncio
    async def test_contrasena_justa_avisa_pero_guarda(self, ajustes):
        _, guardado, _ = ajustes
        r = await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="x" * LONGITUD_MINIMA, base_url="")
        assert r.error is None and r.aviso is not None
        assert guardado

    @pytest.mark.asyncio
    async def test_sin_cambios_de_credenciales_no_se_cierran_las_sesiones(self, ajustes):
        """Guardar solo la `base_url` no debe invalidar la sesión de nadie."""
        actuales, guardado, limpiar = ajustes
        actuales.auth_mode = "password"
        actuales.auth_password_hash = "pbkdf2…"
        r = await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="", base_url="https://a.org/")
        assert not r.cambia_credenciales
        assert "auth_session_version" not in guardado[0]
        assert guardado[0]["base_url"] == "https://a.org"      # sin barra final
        limpiar.assert_not_called()

    @pytest.mark.asyncio
    async def test_modo_desconocido_es_un_error_de_programacion(self, ajustes):
        with pytest.raises(ValueError):
            await fijar_seguridad(MagicMock(), modo="lo-que-sea", usuario="", password="", base_url="")
