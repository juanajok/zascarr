# ruff: noqa: E501
"""El registro de acceso de uvicorn no debe llevar la query (#361).

uvicorn escribe cada petición como `127.0.0.1:1234 - "GET /ruta?clave=…&cursor=…&ref=… HTTP/1.1" 200`. En ZascArr la
query puede llevar datos de la persona: el nombre de una carpeta (`clave`), un cursor que decodifica a un nombre de
archivo, un token firmado de 24 h (`ref`) o lo que se busca (`q`, `consulta`, `titulo`). Una lista de «valores prohibidos»
dejaría fuera los que se añadan después, así que se quita la query ENTERA y se conserva la ruta, que es lo que sirve para
diagnosticar (método, ruta y estado).

Alcance: SOLO el registro de acceso (`uvicorn.access`). No acredita que otros registros, excepciones o un proxy inverso
estén saneados. El filtro actúa antes de que el registro se emita y no toca la petición: las URLs y los enlaces no cambian.
"""
from __future__ import annotations

import logging

#: Lo que queda en lugar de la query, para que quien lea el registro sepa que había una y se le quitó.
MARCA_DE_QUERY_OMITIDA = "?…"
_LOGGER_DE_ACCESO = "uvicorn.access"


def _sin_query(valor: object) -> object:
    if isinstance(valor, str) and "?" in valor:
        return valor.split("?", 1)[0] + MARCA_DE_QUERY_OMITIDA
    return valor


#: Lo que se escribe si no se reconoce el formato del registro (más vale perder la línea que filtrar una query).
REGISTRO_OMITIDO = "(registro de acceso omitido: formato inesperado)"


class SinQueryEnAcceso(logging.Filter):
    """Quita la query de CUALQUIER argumento de texto del registro de acceso (en uvicorn, el tercero: `path?query`).

    **Falla cerrado:** si el formato de los argumentos cambia de una forma que no se sabe tratar (una versión futura de
    uvicorn), el registro se sustituye por `REGISTRO_OMITIDO` en lugar de dejar pasar la línea tal cual."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            if isinstance(args, tuple):
                record.args = tuple(_sin_query(a) for a in args)
            elif isinstance(args, dict):
                record.args = {k: _sin_query(v) for k, v in args.items()}
            elif args is not None:
                raise TypeError("argumentos de registro no reconocidos")
        except Exception:  # noqa: BLE001 — nunca tumba la petición; solo pierde la línea
            record.msg, record.args = REGISTRO_OMITIDO, ()
        return True


def instalar_filtro_de_acceso() -> None:
    """Instala el filtro en `uvicorn.access`. Idempotente: llamarlo varias veces no lo duplica."""
    logger = logging.getLogger(_LOGGER_DE_ACCESO)
    if not any(isinstance(f, SinQueryEnAcceso) for f in logger.filters):
        logger.addFilter(SinQueryEnAcceso())
