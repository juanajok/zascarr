"""
tests/test_cli_seguridad.py

`python -m zascarr.cli.seguridad` (A11): lo que usa el instalador para fijar la
contraseña ANTES de publicar el puerto. El instalador decide por el **código de
salida**, así que eso es lo que se prueba, junto con las dos garantías de
seguridad del diseño: la contraseña solo entra por stdin y nunca sale por la
salida.
"""
from __future__ import annotations

import contextlib
import io
from unittest.mock import AsyncMock, MagicMock

import pytest

from zascarr.cli import seguridad as cli
from zascarr.services import seguridad as servicio

SECRETA = "una frase larga que nadie adivina"


@pytest.fixture
def entorno(monkeypatch):
    """Sustituye BD, ajustes y guardado; devuelve lo que ve el comando."""
    actuales = MagicMock(
        auth_mode="none", auth_username="", auth_password_hash="", auth_session_version=0,
    )
    monkeypatch.setattr(cli, "get_settings", lambda: actuales)
    monkeypatch.setattr(servicio, "get_settings", lambda: actuales)

    db = MagicMock()
    db.commit = AsyncMock()

    @contextlib.asynccontextmanager
    async def _sesion():
        yield db

    monkeypatch.setattr(cli, "async_session_factory", _sesion)
    monkeypatch.setattr(cli, "capturar_valores_base", lambda: None)
    monkeypatch.setattr(cli, "load_overrides_at_startup", AsyncMock())
    monkeypatch.setattr(cli, "engine", MagicMock(dispose=AsyncMock()))

    guardado: list[dict] = []

    async def _save(self, cambios):
        guardado.append(cambios)

    monkeypatch.setattr(servicio.RuntimeSettingsService, "save", _save)
    monkeypatch.setattr(servicio, "limpiar_cache_basic", MagicMock())
    monkeypatch.setattr(servicio, "hash_password_async", AsyncMock(return_value="HASH"))
    return actuales, db, guardado


def _stdin(monkeypatch, texto: str):
    monkeypatch.setattr("sys.stdin", io.StringIO(texto))


class TestEstado:

    def test_sin_contrasena_sale_con_3(self, entorno, capsys):
        assert cli.main(["estado"]) == cli.SIN_CONTRASENA
        assert "ninguna" in capsys.readouterr().out

    def test_con_contrasena_sale_con_0(self, entorno, capsys):
        actuales, _, _ = entorno
        actuales.auth_mode, actuales.auth_password_hash = "password", "pbkdf2…"
        assert cli.main(["estado"]) == cli.OK
        assert "configurada" in capsys.readouterr().out

    def test_modo_con_contrasena_pero_sin_hash_no_cuenta(self, entorno):
        """El mismo criterio que el middleware: sin hash no hay con qué entrar."""
        actuales, _, _ = entorno
        actuales.auth_mode = "password"
        assert cli.main(["estado"]) == cli.SIN_CONTRASENA

    def test_no_imprime_el_hash(self, entorno, capsys):
        actuales, _, _ = entorno
        actuales.auth_mode = "password"
        actuales.auth_password_hash = "pbkdf2_sha256$600000$sal$hash"
        cli.main(["estado"])
        salida = capsys.readouterr()
        assert "pbkdf2" not in salida.out + salida.err


class TestFijarContrasena:

    def test_guarda_y_confirma(self, entorno, monkeypatch, capsys):
        _, db, guardado = entorno
        _stdin(monkeypatch, SECRETA + "\n")
        assert cli.main(["fijar-contrasena"]) == cli.OK
        assert guardado[0]["auth_mode"] == "password"
        assert guardado[0]["auth_password_hash"] == "HASH"
        db.commit.assert_awaited_once()

    def test_la_contrasena_nunca_sale_por_la_salida(self, entorno, monkeypatch, capsys):
        _stdin(monkeypatch, SECRETA + "\n")
        cli.main(["fijar-contrasena"])
        salida = capsys.readouterr()
        assert SECRETA not in salida.out + salida.err

    def test_no_se_guarda_en_claro(self, entorno, monkeypatch):
        _, _, guardado = entorno
        _stdin(monkeypatch, SECRETA + "\n")
        cli.main(["fijar-contrasena"])
        assert SECRETA not in str(guardado)

    def test_corta_se_rechaza_con_2_y_sin_guardar(self, entorno, monkeypatch, capsys):
        _, db, guardado = entorno
        _stdin(monkeypatch, "corta\n")
        assert cli.main(["fijar-contrasena"]) == cli.RECHAZADA
        assert guardado == []
        db.commit.assert_not_awaited()
        assert str(servicio.LONGITUD_MINIMA) in capsys.readouterr().err

    def test_vacia_se_rechaza(self, entorno, monkeypatch):
        _, db, _ = entorno
        _stdin(monkeypatch, "\n")
        assert cli.main(["fijar-contrasena"]) == cli.RECHAZADA
        db.commit.assert_not_awaited()

    def test_los_espacios_de_los_extremos_son_parte_de_la_contrasena(self, entorno, monkeypatch):
        """Solo se quita el salto de línea: `  abc  ` y `abc` son contraseñas distintas."""
        _, _, guardado = entorno
        hasheada: list[str] = []

        async def _hash(p):
            hasheada.append(p)
            return "HASH"

        monkeypatch.setattr(servicio, "hash_password_async", _hash)
        _stdin(monkeypatch, "  " + SECRETA + "  \n")
        cli.main(["fijar-contrasena"])
        assert hasheada == ["  " + SECRETA + "  "]

    def test_justa_avisa_por_stderr_pero_sale_con_0(self, entorno, monkeypatch, capsys):
        _stdin(monkeypatch, "x" * servicio.LONGITUD_MINIMA + "\n")
        assert cli.main(["fijar-contrasena"]) == cli.OK
        assert "Aviso" in capsys.readouterr().err

    def test_no_toca_la_base_url(self, entorno, monkeypatch):
        _, _, guardado = entorno
        _stdin(monkeypatch, SECRETA + "\n")
        cli.main(["fijar-contrasena"])
        assert "base_url" not in guardado[0]


class TestEfectiva:
    """El instalador cuenta lo que va a pasar DE VERDAD, no lo que escribió en el .env."""

    def _ajustar(self, entorno, **campos):
        actuales, _, _ = entorno
        base = {"zascarr_bind_address": "127.0.0.1", "base_url": "", "auth_mode": "none",
                "auth_password_hash": ""}
        for clave, valor in {**base, **campos}.items():
            setattr(actuales, clave, valor)

    def _salida(self, capsys) -> dict:
        return dict(linea.split("=", 1) for linea in capsys.readouterr().out.splitlines())

    def test_por_defecto(self, entorno, capsys):
        self._ajustar(entorno)
        assert cli.main(["efectiva"]) == cli.OK
        assert self._salida(capsys) == {"exposicion": "local", "contrasena": "no", "base_url": ""}

    def test_abierto_a_la_red_con_contrasena(self, entorno, capsys):
        self._ajustar(entorno, zascarr_bind_address="0.0.0.0", auth_mode="password",
                      auth_password_hash="pbkdf2…")
        cli.main(["efectiva"])
        datos = self._salida(capsys)
        assert datos["exposicion"] == "red" and datos["contrasena"] == "si"

    def test_una_base_url_publica_guardada_en_ajustes_cuenta_como_proxy(self, entorno, capsys):
        """El caso del revisor: la de Ajustes manda sobre el .env, y `efectiva` ve la
        resultante (la que ya cargó `load_overrides_at_startup`)."""
        self._ajustar(entorno, base_url="https://vieja.ejemplo.org")
        cli.main(["efectiva"])
        datos = self._salida(capsys)
        assert datos["exposicion"] == "proxy" and datos["base_url"] == "https://vieja.ejemplo.org"

    def test_no_imprime_el_hash_ni_nada_de_la_contrasena(self, entorno, capsys):
        self._ajustar(entorno, auth_mode="password", auth_password_hash="pbkdf2_sha256$600000$s$h")
        cli.main(["efectiva"])
        assert "pbkdf2" not in capsys.readouterr().out

    def test_una_base_url_con_saltos_de_linea_no_inyecta_claves(self, entorno, capsys):
        """El instalador parsea `clave=valor` línea a línea: un valor no puede fabricar otra."""
        self._ajustar(entorno, base_url="https://a.org\ncontrasena=si")
        cli.main(["efectiva"])
        assert self._salida(capsys)["contrasena"] == "no"


class TestRetirarBaseUrl:

    def test_guarda_vacia_para_que_mande_el_env(self, entorno, capsys):
        _, db, guardado = entorno
        assert cli.main(["retirar-base-url"]) == cli.OK
        assert guardado == [{"base_url": ""}]
        db.commit.assert_awaited_once()

    def test_no_toca_la_contrasena(self, entorno):
        _, _, guardado = entorno
        cli.main(["retirar-base-url"])
        assert set(guardado[0]) == {"base_url"}


class TestRobustez:

    def test_la_contrasena_no_se_acepta_como_argumento(self, entorno):
        """Por argumentos quedaría en `ps` y en el historial: el parser no la admite."""
        with pytest.raises(SystemExit) as salida:
            cli.main(["fijar-contrasena", SECRETA])
        assert salida.value.code == 2

    def test_un_error_inesperado_sale_con_1_y_sin_traceback(self, entorno, monkeypatch, capsys):
        monkeypatch.setattr(
            cli, "load_overrides_at_startup", AsyncMock(side_effect=OSError("secreto://x")))
        assert cli.main(["estado"]) == cli.ERROR
        err = capsys.readouterr().err
        assert "OSError" in err
        assert "secreto://x" not in err and "Traceback" not in err
