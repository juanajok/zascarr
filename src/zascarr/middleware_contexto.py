"""Contexto mínimo de cada petición para que sus logs se puedan correlacionar.

No registra una línea nueva por petición: añade `request_id`, `method` y `path`
al contexto de structlog mientras dura la petición. El ID se devuelve en
`X-Request-ID` (si el cliente ya mandaba uno válido, se reutiliza) para poder
cruzarlo con el registro de acceso de uvicorn.
"""
from __future__ import annotations

from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_CABECERA = "X-Request-ID"
_MAX = 64


class ContextoPeticionMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        recibido = request.headers.get(_CABECERA, "").strip()
        request_id = recibido[:_MAX] if recibido else uuid4().hex[:12]
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )
        try:
            respuesta = await call_next(request)
        finally:
            structlog.contextvars.clear_contextvars()
        respuesta.headers[_CABECERA] = request_id
        return respuesta
