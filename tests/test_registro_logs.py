# ruff: noqa: E501
"""Formato, nivel y contexto de logging (mejora de observabilidad)."""
from __future__ import annotations

import json
import logging

import pytest
import structlog
from fastapi.testclient import TestClient

from zascarr.config import Settings
from zascarr.main import app
from zascarr.utils import registro_reciente
from zascarr.utils.registro import configurar_logs, nivel_de_log


@pytest.fixture(autouse=True)
def _config_por_defecto():
    configurar_logs(Settings(log_json=True, log_level="INFO"))
    yield
    configurar_logs(Settings(log_json=True, log_level="INFO"))


def test_nivel_invalido_cae_a_info():
    assert nivel_de_log("verbose") == (logging.INFO, "info")
    assert nivel_de_log("WARN") == (logging.WARNING, "warning")


def test_json_tiene_campos_estables_y_no_duplica_level(capsys):
    logger = structlog.get_logger()
    logger.info("prueba.evento", file_id="abc", request_id="r1")
    salida = capsys.readouterr().out.strip().splitlines()
    assert salida, "no se escribió ninguna línea"
    evento = json.loads(salida[-1])
    assert evento["event"] == "prueba.evento"
    assert evento["level"] == "info"
    assert evento["file_id"] == "abc" and evento["request_id"] == "r1"
    assert evento["timestamp"].endswith("Z")
    assert "log_level" not in evento and "logger" not in evento


def test_log_level_filtra_de_verdad(capsys):
    logger = structlog.get_logger()
    logger.debug("no.debe.salir")
    logger.error("si.debe.salir")
    lineas = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.strip()]
    assert [x["event"] for x in lineas] == ["si.debe.salir"]
    assert lineas[0]["level"] == "error"


def test_formato_consola_si_se_desactiva_json(capsys):
    configurar_logs(Settings(log_json=False, log_level="INFO"))
    structlog.get_logger().info("consola.evento", foo="bar")
    salida = capsys.readouterr().out
    assert "consola.evento" in salida and "foo=bar" in salida
    assert not salida.lstrip().startswith("{")


def test_el_texto_descargado_no_repite_el_nivel():
    registro_reciente.limpiar()
    registro_reciente.capturar(None, "info", {
        "event": "prueba", "log_level": "info", "level": "info",
        "timestamp": "2026-11-17T10:00:00Z", "file_id": "f1",
    })
    texto = registro_reciente.texto_reciente()
    assert "level=info" not in texto and "log_level=" not in texto
    assert "file_id=f1" in texto
    registro_reciente.limpiar()


def test_la_peticion_lleva_request_id_y_se_conserva_el_del_cliente():
    c = TestClient(app)
    r = c.get("/api/health")
    assert r.status_code == 200 and r.headers.get("x-request-id")
    r2 = c.get("/api/health", headers={"X-Request-ID": "cliente-123"})
    assert r2.headers["x-request-id"] == "cliente-123"


def test_el_middleware_no_filtra_el_request_id_a_otra_peticion():
    c = TestClient(app)
    primero = c.get("/api/health").headers["x-request-id"]
    segundo = c.get("/api/health").headers["x-request-id"]
    assert primero != segundo


def test_el_request_id_llega_al_contexto_de_la_peticion():
    from fastapi import FastAPI

    from zascarr.middleware_contexto import ContextoPeticionMiddleware

    prueba = FastAPI()
    prueba.add_middleware(ContextoPeticionMiddleware)

    @prueba.get("/log")
    async def _log():
        return dict(structlog.contextvars.get_contextvars())

    r = TestClient(prueba).get("/log")
    assert r.status_code == 200
    assert r.json()["request_id"] == r.headers["x-request-id"]
    assert r.json()["method"] == "GET" and r.json()["path"] == "/log"
