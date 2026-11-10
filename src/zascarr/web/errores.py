"""
Página de error propia (revisión visual, 2026-10-20).

Un enlace roto o una serie borrada enseñaban `{"detail":"Serie no encontrada"}` en crudo: fuera
de la app, sin menú y sin forma de volver. Y los 503 de «Base de datos no lista» eran HTML suelto,
sin estilos.

Solo para lo que pide una persona navegando: GET, sin HTMX y fuera de /api/.
- La API sigue con su JSON (hay clientes y pruebas que leen `detail`).
- Una petición HTMX conserva su respuesta y sus cabeceras (HX-Redirect del aviso legal…): la página
  entera acabaría metida dentro del fragmento que esperaba el `hx-target`.
- Un POST de formulario mantiene su contrato (409/422 con `detail` estructurado).

La página no toca la BD (puede ser justo lo que falla) y, si pintarla falla, cae a un HTML mínimo.
"""
from __future__ import annotations

from html import escape
from http import HTTPStatus

import structlog
from fastapi import Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from zascarr.web.routes import crear_templates

logger = structlog.get_logger()
templates = crear_templates()

#: código → (rótulo de ≤ 3 palabras, frase llana). Sin códigos en superficie (CLAUDE.md §6).
_TEXTOS: dict[int, tuple[str, str]] = {
    404: ("No está aquí",
          "Esta página no existe, o lo que buscabas ya no está: quizá se borró o cambió de sitio."),
    401: ("Sin permiso", "Necesitas entrar con tu contraseña para ver esta página."),
    403: ("Sin permiso", "No puedes abrir esta página."),
    503: ("No disponible", "ZascArr no puede atender esta página ahora mismo."),
}
_GENERICO = ("Algo ha fallado",
             "ZascArr no ha podido mostrar esta página. Prueba otra vez dentro de un momento; "
             "si se repite, mira el Estado.")


def quiere_pagina(request: Request) -> bool:
    """¿La pide una persona navegando? (ver el docstring del módulo)."""
    return (request.method in ("GET", "HEAD")
            and "hx-request" not in request.headers
            and not request.url.path.startswith("/api/"))


def _es_frase(detalle: object, status: int) -> bool:
    """Un `detail` que se puede enseñar: texto con espacios, no un código
    («legal_acknowledgment_required») ni la frase genérica de Starlette en inglés («Not Found»)."""
    if not isinstance(detalle, str) or " " not in detalle.strip():
        return False
    try:
        return detalle != HTTPStatus(status).phrase
    except ValueError:
        return True


def pagina_error(request: Request, status: int, *, titulo: str | None = None,
                 mensaje: str | None = None, detalle: str | None = None,
                 headers: dict[str, str] | None = None) -> HTMLResponse:
    rotulo, frase = _TEXTOS.get(status, _GENERICO)
    titulo, mensaje = titulo or rotulo, mensaje or frase
    try:
        return templates.TemplateResponse(request, "error.html", {
            "titulo": titulo, "mensaje": mensaje, "detalle": detalle,
            "enlace_estado": status >= 500,
        }, status_code=status, headers=headers)
    except Exception:
        # La página de error no puede convertirse en otro error: HTML mínimo, sin plantilla.
        logger.exception("pagina_error.pintado_fallido", status=status)
        return HTMLResponse(
            f"<h1>{escape(titulo)}</h1><p>{escape(mensaje)}</p>"
            '<p><a href="/ui/">Ir al Inicio</a> · <a href="/estado">Ver el estado</a></p>',
            status_code=status, headers=headers)


async def manejar_http(request: Request, exc: StarletteHTTPException) -> Response:
    if not quiere_pagina(request):
        return await http_exception_handler(request, exc)
    detalle = exc.detail if _es_frase(exc.detail, exc.status_code) else None
    return pagina_error(request, exc.status_code, detalle=detalle,
                        headers=getattr(exc, "headers", None))


async def manejar_inesperado(request: Request, exc: Exception) -> Response:
    """500. Starlette lo registra y lo vuelve a lanzar después: aquí solo se decide qué se ve."""
    if not quiere_pagina(request):
        return PlainTextResponse("Internal Server Error", status_code=500)
    return pagina_error(request, 500)
