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
    """La URL pública de un proxy inverso con TLS: `https://dominio[:puerto]`, sin más."""

    @pytest.mark.parametrize("url", [
        "https://tebeos.ejemplo.org",
        "https://tebeos.ejemplo.org:8443",
        "https://localhost",
        "https://xn--ndalo-ysa.es",            # punycode: lo que el navegador envía en Origin
        "https://192.168.1.50",
        "https://a.org:1", "https://a.org:65535",
    ])
    def test_acepta(self, url):
        assert url_publica_valida(url)

    @pytest.mark.parametrize("url", [
        "", "  ", "tebeos.ejemplo.org", "http://tebeos.ejemplo.org",
        "https://", "https:///ruta", "ftp://ejemplo.org", "javascript:alert(1)",
        "https://a b.org", "https://u@a.org", "https://a.org?x=1",
    ])
    def test_rechaza_lo_que_no_es_una_url_https(self, url):
        assert not url_publica_valida(url)

    @pytest.mark.parametrize("url", [
        "https://ejemplo.org/zascarr", "https://ejemplo.org/",
    ])
    def test_rechaza_rutas_porque_no_hay_soporte_probado_bajo_un_prefijo(self, url):
        assert not url_publica_valida(url)

    @pytest.mark.parametrize("url", [
        "https://a.org:0", "https://a.org:65536", "https://a.org:99999", "https://a.org:",
        "https://a.org:123456",
    ])
    def test_rechaza_puertos_fuera_de_rango(self, url):
        assert not url_publica_valida(url)

    @pytest.mark.parametrize("url", [
        "https://999.1.1.1", "https://1.2.3", "https://1.2.3.4.5", "https://01.2.3.4",
        "https://256.0.0.1",
    ])
    def test_un_host_numerico_tiene_que_ser_una_ipv4_de_verdad(self, url):
        assert not url_publica_valida(url)

    @pytest.mark.parametrize("url", ["https://[::1]", "https://[2001:db8::1]:8443", "https://[::1"])
    def test_no_admite_ipv6_literal(self, url):
        """No se valida: un dominio cubre el caso. Mejor rechazarlo que aceptarlo a ciegas."""
        assert not url_publica_valida(url)

    @pytest.mark.parametrize("url", [
        "https://a..org", "https://.a.org", "https://a.org.", "https://-a.org", "https://a-.org",
        "https://" + "a" * 64 + ".org", "https://" + ".".join(["abcdefghi"] * 30) + ".org",
    ])
    def test_rechaza_nombres_de_host_mal_formados(self, url):
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
        r = await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="",
            base_url="",
        )
        assert r.error == seguridad.MENSAJE_SIN_CONTRASENA
        assert guardado == []

    @pytest.mark.asyncio
    async def test_activar_password_con_una_ya_guardada_no_exige_reescribirla(self, ajustes):
        actuales, guardado, _ = ajustes
        actuales.auth_password_hash = "pbkdf2…"
        r = await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="",
            base_url="",
        )
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
        r = await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="corta",
            base_url="",
        )
        assert r.error == seguridad.MENSAJE_CORTA
        assert guardado == []

    @pytest.mark.asyncio
    async def test_contrasena_nueva_hashea_sube_version_y_limpia_la_cache(self, ajustes):
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
    async def test_base_url_none_no_la_toca(self, ajustes):
        """El instalador no debe pisar la `base_url` que el coleccionista puso en
        Ajustes (cadena vacía significaría «vuelve al .env»)."""
        _, guardado, _ = ajustes
        await fijar_seguridad(
            MagicMock(), modo="password", usuario="", password="x" * 15,
            base_url=None,
        )
        assert "base_url" not in guardado[0]

    @pytest.mark.asyncio
    async def test_modo_desconocido_es_un_error_de_programacion(self, ajustes):
        with pytest.raises(ValueError):
            await fijar_seguridad(
                MagicMock(), modo="lo-que-sea", usuario="", password="", base_url="")
