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


class SinQueryEnAcceso(logging.Filter):
    """Reescribe el tercer argumento del registro de acceso de uvicorn (`path?query`) dejando solo `path`."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            args = record.args
            # Formato de uvicorn: '%s - "%s %s HTTP/%s" %d' → (cliente, método, ruta+query, versión, estado).
            if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str) and "?" in args[2]:
                record.args = (*args[:2], args[2].split("?", 1)[0] + MARCA_DE_QUERY_OMITIDA, *args[3:])
        except Exception:  # noqa: BLE001 — un registro raro nunca debe tumbar la petición ni dejar de salir
            pass
        return True


def instalar_filtro_de_acceso() -> None:
    """Instala el filtro en `uvicorn.access`. Idempotente: llamarlo varias veces no lo duplica."""
    logger = logging.getLogger(_LOGGER_DE_ACCESO)
    if not any(isinstance(f, SinQueryEnAcceso) for f in logger.filters):
        logger.addFilter(SinQueryEnAcceso())
