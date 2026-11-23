# ruff: noqa: E501
"""Cabeceras de seguridad en TODAS las respuestas HTTP (#1229; propuesta 11 de #1227, dictamen de SecOps).

Middleware ASGI **puro**: solo toca el mensaje `http.response.start` y deja pasar el cuerpo tal cual,
así que no bufferiza (streaming de CBZ e imágenes, presupuesto de 512 M en la Pi). Por eso no es un
`BaseHTTPMiddleware`. Se añade el último en `create_app` para quedar el más externo y cubrir también
los 401/403/404/413, las redirecciones del `AuthMiddleware` y `/static`.

Una cabecera que la ruta ya fijó (p. ej. `nosniff` de OPDS, lector o portadas, o un `X-Robots-Tag`) no
se pisa ni se duplica; `Cache-Control` no se toca.

**La CSP no lleva `script-src` ni `style-src` a propósito** (`hx-on` evalúa con `Function`, hay plantillas
con `<script>` y `style=`): solo `frame-ancestors`, `base-uri`, `form-action` y `object-src`. Sin HSTS:
hay instalaciones en HTTP por la LAN (ADR 0004).
"""
from __future__ import annotations

#: (nombre en minúsculas, valor). Los valores los fija SecOps (#1229).
CABECERAS_DE_SEGURIDAD: tuple[tuple[bytes, bytes], ...] = (
    (b"x-frame-options", b"DENY"),
    (b"content-security-policy",
     b"frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
    (b"x-robots-tag", b"noindex"),
)


def completar_cabeceras(cabeceras: list[tuple[bytes, bytes]]) -> list[tuple[bytes, bytes]]:
    """Cabeceras crudas ASGI más las de seguridad que falten (comparación sin distinguir mayúsculas)."""
    presentes = {nombre.lower() for nombre, _ in cabeceras}
    return cabeceras + [par for par in CABECERAS_DE_SEGURIDAD if par[0] not in presentes]


def aplicar_a_respuesta(respuesta) -> None:
    """Mismo criterio sobre una respuesta de Starlette (`setdefault`), para los 500 que genera
    `ServerErrorMiddleware`, que queda por fuera de cualquier middleware de usuario."""
    for nombre, valor in CABECERAS_DE_SEGURIDAD:
        respuesta.headers.setdefault(nombre.decode("ascii"), valor.decode("ascii"))


class CabecerasDeSeguridadMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        async def enviar(mensaje):
            if mensaje.get("type") == "http.response.start":
                mensaje = {**mensaje,
                           "headers": completar_cabeceras(list(mensaje.get("headers") or []))}
            await send(mensaje)

        await self.app(scope, receive, enviar)
