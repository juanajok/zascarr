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


def test_ajustes_usa_la_misma_funcion():
    """CLAUDE.md §3.1.1: la prueba de conexión de Ajustes no duplica el protocolo."""
    from zascarr.web import ajustes

    assert ajustes.hash_contrasena_amuleweb is hash_contrasena_amuleweb


class _Respuesta:
    cookies = {"amuleweb_session_id": "abc"}
    headers: dict = {}


class _Cliente:
    enviado: dict = {}

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, data):
        _Cliente.enviado = data
        return _Respuesta()


@pytest.mark.asyncio
async def test_el_login_envia_el_hash_y_no_lo_escribe_en_los_logs(monkeypatch):
    monkeypatch.setattr(amule_mod.httpx, "AsyncClient", _Cliente)
    cliente = AMuleClient()
    cliente._base, cliente._password = "http://127.0.0.1:4711", CONTRASENA
    with structlog.testing.capture_logs() as registros:
        assert await cliente.login()
    esperado = hash_contrasena_amuleweb(CONTRASENA)
    assert _Cliente.enviado == {"p": esperado}
    texto = repr(registros)
    assert esperado not in texto and CONTRASENA not in texto
