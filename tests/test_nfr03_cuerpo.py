# ruff: noqa: E501
"""NFR-03 (#363): límite del cuerpo antes de leerlo entero."""
from __future__ import annotations

from urllib.parse import urlencode

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from zascarr.config import get_settings
from zascarr.main import create_app
from zascarr.middleware_cuerpo import LimiteCuerpoMiddleware
from zascarr.services.tokens_revision import MAX_TOKEN_VINCULACION

LIMITE = 1024


async def _llamar(app, *, method="POST", headers=(), mensajes=None):
    enviado = []
    recibido = []

    async def receive():
        if mensajes:
            return mensajes.pop(0)
        recibido.append(True)
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(mensaje):
        enviado.append(mensaje)

    async def destino(scope, recv, send_):
        recibido.append("app")
        await recv()
        await send_({"type": "http.response.start", "status": 204, "headers": []})
        await send_({"type": "http.response.body", "body": b""})

    scope = {"type": "http", "method": method, "path": "/", "headers": list(headers)}
    await app(destino)(scope, receive, send)
    return recibido, enviado


@pytest.mark.asyncio
async def test_content_length_excesivo_se_rechaza_sin_llamar_a_la_app_ni_leer():
    recibido, enviado = await _llamar(
        lambda app: LimiteCuerpoMiddleware(app, max_bytes=LIMITE),
        headers=[(b"content-length", b"999999")], mensajes=[])
    assert recibido == []
    assert enviado[0]["status"] == 413
    assert b"demasiado grande" in b"".join(m.get("body", b"") for m in enviado)


@pytest.mark.asyncio
async def test_la_cabecera_falsa_no_evita_el_limite_de_los_bytes_reales():
    recibido, enviado = await _llamar(
        lambda app: LimiteCuerpoMiddleware(app, max_bytes=LIMITE),
        headers=[(b"content-length", b"10")],
        mensajes=[{"type": "http.request", "body": b"x" * 2000, "more_body": False}])
    assert recibido == []
    assert enviado[0]["status"] == 413


@pytest.mark.asyncio
async def test_chunked_sin_cabecera_corta_al_pasarse_antes_de_terminar():
    recibido, enviado = await _llamar(
        lambda app: LimiteCuerpoMiddleware(app, max_bytes=LIMITE),
        headers=[],
        mensajes=[
            {"type": "http.request", "body": b"x" * 700, "more_body": True},
            {"type": "http.request", "body": b"y" * 700, "more_body": True},
        ])
    assert recibido == []
    assert enviado[0]["status"] == 413


@pytest.mark.asyncio
async def test_cuerpo_pequeno_pasa_y_se_reproduce():
    recibido, enviado = await _llamar(
        lambda app: LimiteCuerpoMiddleware(app, max_bytes=LIMITE),
        headers=[(b"content-length", b"2")],
        mensajes=[{"type": "http.request", "body": b"ok", "more_body": False}])
    assert "app" in recibido and recibido[0] == "app"
    assert enviado[0]["status"] == 204


@pytest.mark.asyncio
async def test_get_no_se_limita():
    recibido, enviado = await _llamar(
        lambda app: LimiteCuerpoMiddleware(app, max_bytes=LIMITE),
        method="GET", headers=[(b"content-length", b"999999")])
    assert "app" in recibido and enviado[0]["status"] == 204


def test_el_tope_por_defecto_supera_con_margen_el_cuerpo_valido_maximo_de_115():
    campos = [
        ("token", "x" * MAX_TOKEN_VINCULACION),
        ("cursor_actual", "z" * 200),
        ("pagina_desde", "1"),
        ("pagina_hasta", "100"),
    ]
    cuerpo_valido = len(urlencode(campos).encode("utf-8"))
    assert get_settings().max_cuerpo_peticion_bytes >= cuerpo_valido * 3


def test_una_ruta_real_responde_413_antes_de_parsear_el_cuerpo():
    # No llega a la ruta: el middleware responde antes de que FastAPI valide el
    # formulario (el cuerpo no es un token válido ni hace falta que lo sea).
    app = FastAPI()
    app.add_middleware(LimiteCuerpoMiddleware, max_bytes=1024)

    @app.post("/escritura")
    async def escritura(_request: Request):
        return {"ok": True}

    with TestClient(app) as c:
        r = c.post("/escritura", content=b"x" * 2000)
    assert r.status_code == 413
    assert "demasiado grande" in r.text


def test_una_ruta_real_de_zascarr_rechaza_antes_de_parsear_el_formulario():
    """No necesita base: el cuerpo se corta antes de llegar a la validación del token."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post("/api/revision/vinculacion", content=b"token=" + b"x" * 300_000,
                   headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status_code == 413
    assert "demasiado grande" in r.text
