# ruff: noqa: E501
"""SEC-LOG (#369): ayuda de saneado, búfer y llamadas inventariadas."""
from __future__ import annotations

import ast

import structlog
from structlog.testing import capture_logs

from zascarr.utils import registro_reciente as rr
from zascarr.utils.log_privacidad import (
    ARCHIVO,
    RUTA,
    URL,
    error_para_log,
    nombre_para_log,
    ruta_para_log,
    sanear_evento,
    sanear_texto,
    url_para_log,
)

INVENTARIO = (
    "services/importer.py", "services/library_adopter.py", "services/tagger.py",
    "services/library_audit.py", "utils/cbz.py", "services/forum_scraper.py",
    "services/discovery.py", "services/blog_feed.py",
    "services/exportacion_kavita.py", "utils/cover.py", "web/ajustes.py",
)


def test_los_ayudantes_no_devuelven_rutas_ni_nombres():
    assert ruta_para_log("/media/WDElements/Tebeos/Batman 001.cbz") == RUTA
    assert nombre_para_log("Batman 001.cbz") == ARCHIVO
    assert url_para_log("https://foro.example/index.php?act=Search&CODE=01&s=secreto") == URL
    assert error_para_log(FileNotFoundError("/media/WDElements/x.cbz")) == "FileNotFoundError"
    texto = sanear_texto("falló /media/WDElements/Tebeos/Batman 001.cbz y https://x/y?s=1")
    assert "WDElements" not in texto and "Batman" not in texto and "x/y" not in texto
    assert RUTA in texto and "https://x" in texto


def test_el_procesador_sanea_claves_rutas_urls_y_excepciones():
    evento = sanear_evento(None, "error", {
        "event": "fallo", "file": "Batman 001.cbz", "ruta": "/media/x.cbz",
        "mensaje": "no existe /media/WDElements/Tebeos/x.cbz",
        "url": "https://foro.example/?s=secreto",
        "exc_info": (ValueError, ValueError("/media/WDElements/x.cbz"), None),
    })
    serializado = repr(evento)
    assert "Batman" not in serializado and "WDElements" not in serializado
    assert "secreto" not in serializado and "foro.example" not in serializado
    assert evento["file"] == ARCHIVO and evento["ruta"] == RUTA
    assert evento["exc_info"] is False and evento["error_type"] == "ValueError"


def test_el_buffer_de_logs_tambien_sanea_rutas_y_excepciones():
    rr.instalar_captura()
    rr.limpiar()
    structlog.get_logger("prueba").info(
        "evento.con.ruta", ruta="/media/WDElements/Tebeos/Batman 001.cbz")
    structlog.get_logger("prueba").exception(
        "evento.con.excepcion", exc_info=FileNotFoundError("/media/WDElements/x.cbz"))
    texto = rr.texto_reciente()
    assert "WDElements" not in texto and "Batman" not in texto
    assert RUTA in texto and "FileNotFoundError" in texto


def test_captura_con_testing_no_es_la_red_de_seguridad_pero_las_llamadas_usan_los_ayudantes():
    with capture_logs() as registros:
        structlog.get_logger("prueba").warning(
            "forum.search_rechazada", error=error_para_log(ValueError("https://foro.example/?s=x")))
    assert registros[-1]["error"] == "ValueError"


def _llamadas_de_log(ruta):
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Attribute)
            and nodo.func.attr in {"info", "warning", "error", "exception", "debug"}
            and isinstance(nodo.func.value, ast.Name)
            and nodo.func.value.id == "logger"
        ):
            yield nodo


def test_las_llamadas_inventariadas_no_pasan_rutas_crudas_ni_str_exc():
    raiz = __import__("pathlib").Path(__file__).resolve().parents[1] / "src/zascarr"
    peligrosas = []
    for rel in INVENTARIO:
        for nodo in _llamadas_de_log(raiz / rel):
            for kw in nodo.keywords:
                valor = ast.unparse(kw.value) if kw.value is not None else ""
                if kw.arg in {"path", "ruta", "archivo", "file", "root", "raiz", "dir", "destino", "url"}:
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        continue
                    if isinstance(kw.value, ast.Name) and kw.value.id in {"nombre"}:
                        continue
                    if not any(n in valor for n in ("nombre_para_log", "ruta_para_log", "url_para_log")):
                        peligrosas.append((rel, nodo.lineno, kw.arg, valor))
                if kw.arg in {"motivo", "error", "causa"} and "str(" in valor:
                    peligrosas.append((rel, nodo.lineno, kw.arg, valor))
    assert peligrosas == []


def test_el_filtro_de_uvicorn_quita_rutas_y_trazas():
    import logging

    from zascarr.utils.log_privacidad import FiltroLogsSinRutas

    registro = logging.LogRecord(
        "uvicorn.error", logging.ERROR, __file__, 1,
        "Exception in ASGI application: /media/WDElements/Tebeos/Batman 001.cbz",
        (), (FileNotFoundError, FileNotFoundError("/media/WDElements/x.cbz"), None))
    assert FiltroLogsSinRutas().filter(registro) is True
    assert "WDElements" not in registro.msg and "Batman" not in registro.msg
    assert "FileNotFoundError" in registro.msg and registro.exc_info is None


def test_un_punto_inventariado_emite_categoria_no_ruta(tmp_path, monkeypatch):
    """CBZ: el fallo de limpieza de temporales no publica la carpeta de la persona."""
    import os

    from zascarr.utils import cbz

    def falla(_ruta):
        raise OSError("permiso denegado en /media/WDElements/Tebeos/Batman 001.cbz")

    monkeypatch.setattr(os, "scandir", falla)
    with capture_logs() as registros:
        cbz._limpiar_temporales_viejos(tmp_path / "Batman 001.cbz")
    evento = registros[-1]
    assert evento["dir"] == RUTA
    assert "WDElements" not in repr(evento) and "Batman" not in repr(evento)
