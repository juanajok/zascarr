"""SEC-LOG (#369): saneo único de logs."""
from __future__ import annotations

import logging
from pathlib import Path

from zascarr.utils import registro_reciente
from zascarr.utils.saneado_logs import (
    FiltroSaneado,
    instalar_filtro_registros,
    instalar_saneo_structlog,
    refrescar_raices,
    sanear_evento,
    sanear_texto,
    sanear_valor,
)

RAIZ = "/media/library"


def test_ruta_nombre_url_y_credenciales():
    texto = ("FileNotFoundError('/media/library/Serie/foo.cbz') "
             "https://user:pass@example.com/a?token=abc password=secreto")
    s = sanear_texto(texto, raices=(RAIZ,))
    assert "/media/library" not in s and "foo.cbz" not in s and "token=abc" not in s
    assert "https://example.com/[url]" in s
    assert ("[ruta]" in s or "[archivo]" in s) and "[credencial]" in s


def test_idempotente_y_anidado():
    evento = {
        "event": "x /media/library/a.cbz",
        "datos": ["/media/library/b.cbz", {"p": "foo.cbr"}],
        "file_id": "abc",
    }
    uno = sanear_evento(None, "info", evento)
    dos = sanear_evento(None, "info", uno)
    assert uno == dos
    assert uno["file_id"] == "abc"
    assert "/media/library" not in str(uno) and "foo.cbr" not in str(uno)


def test_filtro_excepcion_no_cambia_nivel():
    refrescar_raices([RAIZ])
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                               "fallo en /media/library/a.cbz", (), None)
    try:
        raise FileNotFoundError("/media/library/Serie/foo.cbz")
    except FileNotFoundError:
        import sys
        record.exc_info = sys.exc_info()
    assert FiltroSaneado().filter(record) is True
    assert record.levelno == logging.ERROR
    assert "/media/library" not in record.msg and "/media/library" not in (record.exc_text or "")
    assert ("[ruta]" in (record.exc_text or "") or "[archivo]" in (record.exc_text or ""))


def test_instalacion_idempotente():
    instalar_saneo_structlog()
    instalar_saneo_structlog()
    instalar_filtro_registros()
    instalar_filtro_registros()
    logger = logging.getLogger("uvicorn.error")
    assert sum(isinstance(f, FiltroSaneado) for f in logger.filters) <= 1


def test_buffer_guarda_saneado():
    registro_reciente.limpiar()
    saneado = sanear_evento(None, "info", {"event": "x /media/library/a.cbz"})
    from zascarr.utils.registro_reciente import capturar
    capturar(None, "info", saneado)
    assert "/media/library" not in registro_reciente.texto_reciente()


def test_absolutas_espacios_relativa_y_url_bd():
    refrescar_raices(["/media/library"])
    assert "/tmp" not in sanear_texto("/tmp/with space/foo.cbz")
    assert "Serie" not in sanear_texto("Serie/foo.cbz")
    assert "user:pass" not in sanear_texto("postgresql+asyncpg://user:pass@host/db")
    assert "host/[url]" in sanear_texto("postgresql+asyncpg://user:pass@host/db")


def test_valores_path_excepcion_y_objetos():
    from pathlib import Path
    assert "/media" not in str(sanear_valor(Path("/media/library/a.cbz")))
    assert "/media" not in str(sanear_valor(FileNotFoundError("/media/library/a.cbz")))

    class Raro:
        def __repr__(self):
            return "/media/library/raro.cbz"
    assert "/media" not in str(sanear_valor(Raro()))


def test_filtro_extra_stack_y_handler_posterior():
    refrescar_raices([RAIZ])
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "ok", (), None)
    record.extra = "/media/library/a.cbz"
    record.stack_info = "File \"/media/library/a.cbz\""
    FiltroSaneado().filter(record)
    assert "/media/library" not in record.extra and "/media/library" not in record.stack_info
    handler = logging.StreamHandler()
    logging.getLogger().addHandler(handler)
    try:
        instalar_filtro_registros()
        assert any(isinstance(f, FiltroSaneado) for f in handler.filters)
    finally:
        logging.getLogger().removeHandler(handler)


def test_caplog_5xx_real_sin_ruta(caplog):
    refrescar_raices([RAIZ])
    instalar_filtro_registros()
    logger = logging.getLogger("uvicorn.error")
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        try:
            raise FileNotFoundError("/media/library/Serie/foo.cbz")
        except FileNotFoundError:
            logger.exception("Exception in ASGI application")
    assert caplog.records and caplog.records[0].levelno == logging.ERROR
    assert "/media/library" not in caplog.text


def test_benchmark_saneo():
    import time
    refrescar_raices([RAIZ])
    texto = "x " * 500
    inicio = time.perf_counter()
    for _ in range(10_000):
        sanear_texto(texto)
    assert time.perf_counter() - inicio < 10


def test_codigo_app_se_conserva_y_websocket_se_sanea():
    refrescar_raices([RAIZ])
    assert "/app/src/zascarr/services/x.py" in sanear_texto(
        'File "/app/src/zascarr/services/x.py", line 10')
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                               "WebSocket /media/library/foo.cbz?token=x", (), None)
    FiltroSaneado().filter(record)
    assert "/media/library" not in record.msg and "foo.cbz" not in record.msg


def test_refrescar_raices_une_config_y_bd(monkeypatch):
    from zascarr.config import get_settings
    from zascarr.utils import saneado_logs
    monkeypatch.setenv("LIBRARY_PATH", "/media/library")
    monkeypatch.setenv("TRANSMISSION_DOWNLOAD_DIR", "/media/downloads")
    monkeypatch.setenv("COVERS_CACHE_PATH", "/media/covers")
    get_settings.cache_clear()
    try:
        refrescar_raices(["/config/raiz"])
        for raiz in ("/media/library", "/media/downloads", "/media/covers", "/config/raiz"):
            assert any(raiz in r for r in saneado_logs._raices)
    finally:
        get_settings.cache_clear()


def test_inventario_control_negativo_politica():
    refrescar_raices([RAIZ])
    casos = ["/media/library/a.cbz", "a.cbz", "https://host/x?token=1",
             "postgresql://u:p@host/db", "/config/covers/a.webp"]
    for caso in casos:
        assert caso not in sanear_texto(caso)
        # control negativo real: el mismo valor en un LogRecord sin filtro se conserva
        record = logging.LogRecord("prueba.crudo", logging.ERROR, __file__, 1,
                                   "%s", (caso,), None)
        assert caso in record.getMessage()
        FiltroSaneado().filter(record)
        assert caso not in record.getMessage()


def test_orden_real_sanitizador_y_captura():
    import structlog

    from zascarr.utils import registro_reciente
    registro_reciente.instalar_captura()
    instalar_saneo_structlog()
    nombres = [getattr(p, "__name__", "") for p in structlog.get_config()["processors"]]
    i_exc = next((i for i, n in enumerate(nombres) if "exc_info" in n), 10**6)
    i_san = nombres.index("sanear_evento") if "sanear_evento" in nombres else 10**6
    i_cap = nombres.index("capturar") if "capturar" in nombres else 10**6
    assert i_exc < i_san < i_cap


def test_benchmark_p50_p95():
    import statistics
    import time
    refrescar_raices([RAIZ])
    texto = "x" * 1000
    tiempos = []
    for _ in range(2000):
        t = time.perf_counter()
        sanear_texto(texto)
        tiempos.append((time.perf_counter() - t) * 1000)
    tiempos.sort()
    assert tiempos[int(len(tiempos) * 0.95)] < 1.0
    assert statistics.median(tiempos) < 1.0


def test_websocket_con_args_se_sanea():
    refrescar_raices([RAIZ])
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                               "WebSocket %s", ("/media/library/x.cbz",), None)
    FiltroSaneado().filter(record)
    assert "/media/library" not in str(record.msg) and "x.cbz" not in str(record.msg)


def test_control_negativo_inventario():
    refrescar_raices([RAIZ])
    casos = [
        ("importer.file_failed", {"file": "foo.cbz", "error": "/media/library/foo.cbz"}),
        ("importer.imported", {"file": "foo.cbz", "relative": "Serie/foo.cbz"}),
        ("importer.recuperado", {"file": "foo.cbz"}),
        ("library_audit.hash_failed", {"path": "/media/library/foo.cbz"}),
        ("cbz.temporal_no_borrado", {"path": "/media/library/foo.cbz"}),
        ("discovery.source_failed", {"error": "https://host/x?token=1"}),
        ("ajustes.test_failed", {"error": "/media/library/foo.cbz"}),
        ("exportacion_kavita.materializar", {"destino": "/media/library/foo.cbz"}),
        ("tagger.reconciliado", {"path": "/media/library/foo.cbz"}),
        ("forum.search_rechazada", {"motivo": "https://host/x?token=1"}),
        ("cover.url_rechazada", {"motivo": "https://host/x?token=1"}),
        ("blog_feed.lectura_fallida", {"url": "https://host/x?token=1"}),
        ("robots.parse_fallido", {"origen": "https://host/x?token=1"}),
    ]
    for evento, datos in casos:
        crudo = str({"event": evento, **datos})
        saneado = str(sanear_evento(None, "error", {"event": evento, **datos}))
        for valor in datos.values():
            if any(c in valor for c in ("/", "?", ".cbz", ".cbr")):
                assert valor in crudo
                assert valor not in saneado, (evento, saneado)


def test_logger_exception_real_y_buffer():
    import structlog

    from zascarr.utils import registro_reciente
    from zascarr.utils.saneado_logs import instalar_saneo_structlog
    registro_reciente.instalar_captura()
    instalar_saneo_structlog()
    registro_reciente.limpiar()
    try:
        raise FileNotFoundError("/media/library/Serie/foo.cbz")
    except FileNotFoundError:
        structlog.get_logger("prueba").exception("fallo real")
    texto = registro_reciente.texto_reciente()
    assert "/media/library" not in texto and "foo.cbz" not in texto


def test_aviso_y_descarga_logs_saneados():
    estado = Path("src/zascarr/web/templates/estado.html").read_text()
    dashboard = Path("src/zascarr/web/templates/dashboard.html").read_text()
    assert "Registro de la aplicación" in estado
    assert "sin rutas, nombres, contraseñas ni tokens" in estado
    assert "Descargar logs" not in dashboard and "/ui/logs" not in dashboard


def test_websocket_con_args_saneado():
    refrescar_raices([RAIZ])
    record = logging.LogRecord("uvicorn.error", logging.ERROR, __file__, 1,
                               "WebSocket /media/library/x.cbz", (42,), None)
    FiltroSaneado().filter(record)
    assert "/media/library" not in str(record.msg) and "x.cbz" not in str(record.msg)


def test_handler_posterior_sin_reinstalar():
    import io
    refrescar_raices([RAIZ])
    instalar_filtro_registros()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("prueba.posterior")
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.error("fallo /media/library/Serie/foo.cbz")
    finally:
        logger.removeHandler(handler)
    assert "/media/library" not in stream.getvalue() and "foo.cbz" not in stream.getvalue()


def test_ruta_abs_multilinea_parentesis_y_file_url():
    refrescar_raices([RAIZ])
    assert "with space" not in sanear_texto("/tmp/with space/foo.jpg (permiso)")
    assert "Permission denied" in sanear_texto("/tmp/with space/foo.jpg: Permission denied")
    multilinea = "Error:\n/media/library/Serie/foo.cbz\nfin"
    s = sanear_texto(multilinea)
    assert "/media/library" not in s and "fin" in s
    assert "/media/library" not in sanear_texto("file:///media/library/a.cbz")


def test_library_roots_config_se_dividen(monkeypatch):
    from zascarr.config import get_settings
    from zascarr.utils import saneado_logs
    monkeypatch.setenv("LIBRARY_ROOTS", "/media/a,/media/b;/config/c")
    get_settings.cache_clear()
    try:
        refrescar_raices()
        for r in ("/media/a", "/media/b", "/config/c"):
            assert any(r in x for x in saneado_logs._raices)
    finally:
        get_settings.cache_clear()


def test_codigo_app_no_se_redacta():
    assert "/app/src/zascarr/services/x.py" in sanear_texto(
        'File "/app/src/zascarr/services/x.py", line 10')


def test_fabrica_sanea_exc_info_en_handler_posterior():
    import io
    refrescar_raices([RAIZ])
    instalar_filtro_registros()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s\n%(exc_text)s"))
    logger = logging.getLogger("prueba.exc.posterior")
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    try:
        try:
            raise FileNotFoundError("/media/library/Serie/foo.cbz")
        except FileNotFoundError:
            logger.exception("fallo")
    finally:
        logger.removeHandler(handler)
    assert "/media/library" not in stream.getvalue() and "foo.cbz" not in stream.getvalue()
    assert "FileNotFoundError" in stream.getvalue()


def test_ruta_desconocida_final_linea_y_guion():
    s = sanear_texto("error en /tmp/foo.jpg - error")
    assert "/tmp" not in s and "- error" in s
    s2 = sanear_texto("primera /tmp/foo.jpg\nsegunda línea")
    assert "/tmp" not in s2 and "segunda línea" in s2


def test_bearer_sin_puntuacion_se_redacta():
    assert "abc123" not in sanear_texto("Bearer abc123")
    assert "[credencial]" in sanear_texto("Authorization Bearer abc123")


def test_handler_posterior_con_formatter_exc_info_no_filtra():
    import io
    refrescar_raices([RAIZ])
    instalar_filtro_registros()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s %(exc_info)s"))
    logger = logging.getLogger("prueba.exc.formatter")
    logger.propagate = False
    logger.setLevel(logging.ERROR)
    logger.addHandler(handler)
    try:
        try:
            raise FileNotFoundError("/media/library/Serie/foo.cbz")
        except FileNotFoundError:
            logger.exception("fallo")
    finally:
        logger.removeHandler(handler)
    assert "/media/library" not in stream.getvalue() and "foo.cbz" not in stream.getvalue()


def test_json_entrecomillado_y_msg_no_str():
    assert "secreto" not in sanear_texto('{"password": "secreto"}')
    assert "secreto" not in sanear_texto('"api_key": "secreto"')
    record = logging.LogRecord("prueba.objeto", logging.ERROR, __file__, 1,
                               Path("/media/library/Serie/foo.cbz"), (), None)
    FiltroSaneado().filter(record)
    assert "/media/library" not in str(record.msg) and "foo.cbz" not in str(record.msg)


def test_inventario_control_negativo_con_registro_real():
    """Cada fila del inventario, con un LogRecord real: crudo filtra, saneado no."""
    from zascarr.utils.saneado_logs import _sanear_record_en_origen
    casos = [
        ("importer.file_failed", {"file": "/media/library/a.cbz", "error": "x.cbz"}),
        ("importer.imported", {"file": "/media/library/a.cbz"}),
        ("importer.recuperado", {"file": "/media/library/a.cbz"}),
        ("library_audit.hash_failed", {"path": "/media/library/a.cbz"}),
        ("cbz.temporal_no_borrado", {"path": "/media/library/a.cbz"}),
        ("discovery.source_failed", {"error": "https://host/x?token=1"}),
        ("ajustes.test_failed", {"error": "/media/library/a.cbz"}),
        ("exportacion_kavita.materializar", {"destino": "/media/library/a.cbz"}),
        ("tagger.reconciliado", {"path": "/media/library/a.cbz"}),
        ("forum.search_rechazada", {"motivo": "https://host/x?token=1"}),
        ("cover.url_rechazada", {"motivo": "https://host/x?token=1"}),
        ("blog_feed.lectura_fallida", {"url": "https://host/x?token=1"}),
        ("robots.parse_fallido", {"origen": "https://host/x?token=1"}),
    ]
    for evento, datos in casos:
        record = logging.LogRecord("zascarr.inventario", logging.ERROR, __file__, 1,
                                   evento, (), None)
        record.__dict__.update(datos)
        crudo = f"{record.getMessage()} {record.__dict__}"
        assert any(v in crudo for v in datos.values()), evento
        _sanear_record_en_origen(record)
        saneado = f"{record.getMessage()} {record.__dict__}"
        for valor in datos.values():
            assert valor not in saneado, (evento, valor, saneado)


def test_stdout_y_buffer_con_logger_real(capsys):
    import structlog

    from zascarr.utils import registro_reciente
    from zascarr.utils.saneado_logs import instalar_saneo_logs
    instalar_saneo_logs()
    registro_reciente.instalar_captura()
    registro_reciente.limpiar()
    try:
        raise FileNotFoundError("/media/library/Serie/foo.cbz")
    except FileNotFoundError:
        structlog.get_logger("prueba.stdout").exception("fallo real")
    salida = capsys.readouterr()
    assert "/media/library" not in salida.out and "foo.cbz" not in salida.out
    texto = registro_reciente.texto_reciente()
    assert "/media/library" not in texto and "foo.cbz" not in texto


def test_filtro_invalida_exc_info_en_registro_directo():
    import io
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s %(exc_info)s"))
    try:
        raise FileNotFoundError("/media/library/Serie/foo.cbz")
    except FileNotFoundError as exc:
        record = logging.LogRecord("prueba.directo", logging.ERROR, __file__, 1,
                                   "fallo directo", (), (type(exc), exc, exc.__traceback__))
    FiltroSaneado().filter(record)
    handler.emit(record)
    assert "/media/library" not in stream.getvalue() and "foo.cbz" not in stream.getvalue()


def test_plantilla_de_uvicorn_con_args_conserva_sus_placeholders():
    """Regresión real: el saneo de `%s://%s/%s` no puede dejar solo dos `%s`."""
    record = logging.LogRecord(
        "uvicorn.error", logging.INFO, __file__, 1,
        "Uvicorn running on %s://%s/%s (Press CTRL+C to quit)",
        ("http", "0.0.0.0", 8000), None)
    FiltroSaneado().filter(record)
    assert record.getMessage() == "Uvicorn running on http://0.0.0.0/8000 (Press CTRL+C to quit)"
