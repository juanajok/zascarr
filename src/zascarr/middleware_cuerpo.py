"""NFR-03 (#363): límite del cuerpo de las peticiones antes de que FastAPI lo parsee.

Comprueba el `Content-Length` declarado y, además, cuenta los bytes realmente
recibidos para cubrir cuerpos `chunked`, sin cabecera o con una cabecera falsa.
Al pasarse del tope responde 413 sin llamar a la aplicación: no hay validación,
ni escritura, ni efectos. El cuerpo válido de #115 mide ~73,5 KiB (token de
73.229 caracteres más campos); el tope por defecto de 256 KiB deja margen >3×.
"""
from __future__ import annotations

from starlette.datastructures import Headers

METODOS_CON_CUERPO = frozenset({"POST", "PUT", "PATCH", "DELETE"})
MENSAJE_DEMASIADO_GRANDE = "La petición es demasiado grande."


class LimiteCuerpoMiddleware:
    """Middleware ASGI puro: no envuelve la respuesta ni toca GET/HEAD."""

    def __init__(self, app, *, max_bytes: int):
        if max_bytes <= 0:
            raise ValueError("El límite del cuerpo debe ser positivo.")
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or scope.get("method") not in METODOS_CON_CUERPO:
            return await self.app(scope, receive, send)

        headers = Headers(scope=scope)
        declarado = headers.get("content-length")
        if declarado is not None:
            try:
                if int(declarado) > self.max_bytes:
                    return await self._rechazar(send)
            except ValueError:
                # Cabecera no numérica: no se confía en ella; se cuenta lo recibido.
                pass

        trozos: list[bytes] = []
        total = 0
        while True:
            mensaje = await receive()
            if mensaje.get("type") == "http.disconnect":
                return
            cuerpo = mensaje.get("body", b"")
            total += len(cuerpo)
            if total > self.max_bytes:
                return await self._rechazar(send)
            trozos.append(cuerpo)
            if not mensaje.get("more_body", False):
                break

        cuerpo_completo = b"".join(trozos)
        entregado = False

        async def replay():
            nonlocal entregado
            if not entregado:
                entregado = True
                return {"type": "http.request", "body": cuerpo_completo, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)

    @staticmethod
    async def _rechazar(send):
        cuerpo = MENSAJE_DEMASIADO_GRANDE.encode("utf-8")
        await send({"type": "http.response.start", "status": 413, "headers": [
            (b"content-type", b"text/plain; charset=utf-8"),
            (b"content-length", str(len(cuerpo)).encode("ascii")),
            (b"cache-control", b"no-store"),
            (b"connection", b"close"),
        ]})
        await send({"type": "http.response.body", "body": cuerpo})
