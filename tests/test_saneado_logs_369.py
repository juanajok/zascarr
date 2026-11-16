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
