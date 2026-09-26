"""Router de autenticación (A6) — /login y /logout.

Sin prefijo /ui a propósito: es una pantalla accesible incluso cuando
AuthMiddleware bloquea todo lo demás (services/auth.py la deja exenta
explícitamente), igual que /legal.
"""
from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from zascarr.config import get_settings
from zascarr.services.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    crear_cookie_sesion,
    credenciales_validas,
)
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(tags=["auth"], include_in_schema=False)


def _next_seguro(destino: str) -> str:
    """`next` llega del query string, así que lo controla quien construye
    el enlace — nunca del propio servidor. Sin este filtro, un enlace tipo
    `/login?next=https://sitio-falso.example` redirigiría tras un login
    correcto a un dominio ajeno (open redirect clásico). Solo se acepta
    una ruta relativa de este mismo sitio."""
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return "/"


@router.get("/login", response_class=HTMLResponse)
async def login_form(request: Request, next: str = "/") -> HTMLResponse:
    next = _next_seguro(next)
    settings = get_settings()
    if settings.auth_mode == "none":
        # Nada que pedir — no tiene sentido enseñar un formulario de
        # contraseña para una instalación que no la tiene activada.
        return RedirectResponse(next)
    return templates.TemplateResponse(request, "login.html", {
        "next": next,
        "pide_usuario": settings.auth_mode == "user_password",
        "error": None,
    })


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request, next: str = Form(default="/"),
    username: str = Form(default=""), password: str = Form(default=""),
) -> HTMLResponse:
    next = _next_seguro(next)
    settings = get_settings()
    if not credenciales_validas(username, password, settings):
        return templates.TemplateResponse(request, "login.html", {
            "next": next,
            "pide_usuario": settings.auth_mode == "user_password",
            "error": "Usuario o contraseña incorrectos.",
        }, status_code=401)

    respuesta = RedirectResponse(next, status_code=303)
    respuesta.set_cookie(
        COOKIE_NAME, crear_cookie_sesion(settings.secret_key),
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    return respuesta


@router.post("/logout")
async def logout() -> RedirectResponse:
    respuesta = RedirectResponse("/login", status_code=303)
    respuesta.delete_cookie(COOKIE_NAME)
    return respuesta
