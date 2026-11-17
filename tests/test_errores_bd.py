"""OCTA-C1: con la base de datos caída, la UI responde 503, no 500."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import InterfaceError, OperationalError

from zascarr.web.errores import manejar_bd_no_disponible


def _app():
    app = FastAPI()
    app.add_exception_handler(OperationalError, manejar_bd_no_disponible)
    app.add_exception_handler(InterfaceError, manejar_bd_no_disponible)

    @app.get("/ui/fallo")
    async def ui_fallo():
        raise OperationalError("SELECT 1", {}, OSError("connection refused"))

    @app.get("/api/fallo")
    async def api_fallo():
        raise InterfaceError("SELECT 1", {}, OSError("connection refused"))

    @app.get("/ui/htmx")
    async def ui_htmx():
        raise OperationalError("SELECT 1", {}, OSError("connection refused"))

    return app


def test_ui_devuelve_503_con_pagina_propia():
    with TestClient(_app()) as client:
        r = client.get("/ui/fallo")
    assert r.status_code == 503
    assert "no puede conectar" in r.text
    assert "Ver el estado" in r.text or "Estado" in r.text


def test_api_devuelve_503_json():
    with TestClient(_app()) as client:
        r = client.get("/api/fallo")
    assert r.status_code == 503
    assert "base de datos" in r.json()["detail"]


def test_htmx_devuelve_503_sin_pagina_completa():
    with TestClient(_app()) as client:
        r = client.get("/ui/htmx", headers={"HX-Request": "true"})
    assert r.status_code == 503
    assert r.text == "No se puede conectar con la base de datos."
