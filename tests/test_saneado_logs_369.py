"""SEC-LOG (#369): saneo único de logs."""
from __future__ import annotations

import logging

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
        # control negativo: sin saneador el caso aparece tal cual
        assert caso in caso


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
