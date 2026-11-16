"""El login de amuleweb (dictamen SecOps del hallazgo S324).

El MD5 de la contraseña lo exige el protocolo de amuleweb y equivale a la contraseña: una sola
implementación (`hash_contrasena_amuleweb`), el valor exacto que espera amuleweb y nunca en logs.
"""
from __future__ import annotations

import pytest
import structlog

from zascarr.services import amule as amule_mod
from zascarr.services.amule import AMuleClient, hash_contrasena_amuleweb

CONTRASENA = "cambia_esto_ahora"
# md5("cambia_esto_ahora"): el campo `p` que amuleweb espera.
HASH = "eca6c4ef90c66a32ce1233d7699697b3"


def test_el_hash_es_el_md5_hexadecimal_que_espera_amuleweb():
    assert hash_contrasena_amuleweb(CONTRASENA) == HASH


def test_ajustes_usa_el_mismo_cliente():
    """CLAUDE.md §3.1.1: la prueba de conexión no duplica el protocolo."""
    from zascarr.web import ajustes

    assert ajustes.AMuleClient is AMuleClient


class _Respuesta:
    cookies = {"amuleweb_session_id": "abc"}
    headers: dict = {}
    text = "aMule control panel"


class _Cliente:
    enviados: list[dict] = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data):
        _Cliente.enviados.append(data)
        return _Respuesta()


@pytest.mark.asyncio
async def test_el_login_envia_el_hash_y_no_lo_escribe_en_los_logs(monkeypatch):
    monkeypatch.setattr(amule_mod.httpx, "AsyncClient", _Cliente)
    cliente = AMuleClient()
    cliente._base, cliente._password = "http://127.0.0.1:4711", CONTRASENA
    with structlog.testing.capture_logs() as registros:
        assert await cliente.login()
    # El amuleweb real espera `pass`; no se manda el hash en el primer intento.
    assert _Cliente.enviados[0] == {"pass": CONTRASENA, "submit": "Submit"}
    texto = repr(registros)
    assert hash_contrasena_amuleweb(CONTRASENA) not in texto and CONTRASENA not in texto


class _ClienteLoginAntiguo:
    """El formato heredado (`p` = MD5) sigue aceptándose si el actual no entra."""
    enviados: list[dict] = []

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data):
        _ClienteLoginAntiguo.enviados.append(data)
        if "pass" in data:
            r = _Respuesta()
            r.text = '<form name="login"><input name="pass"></form>'
            return r
        return _Respuesta()


@pytest.mark.asyncio
async def test_el_login_antiguo_con_p_tambien_funciona(monkeypatch):
    monkeypatch.setattr(amule_mod.httpx, "AsyncClient", _ClienteLoginAntiguo)
    cliente = AMuleClient()
    cliente._base, cliente._password = "http://127.0.0.1:4711", CONTRASENA
    assert await cliente.login()
    assert _ClienteLoginAntiguo.enviados == [
        {"pass": CONTRASENA, "submit": "Submit"},
        {"p": hash_contrasena_amuleweb(CONTRASENA)},
    ]
