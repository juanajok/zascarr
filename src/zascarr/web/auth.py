"""Router de autenticación (A6) — /login y /logout.

Sin prefijo /ui a propósito: es una pantalla accesible incluso cuando
AuthMiddleware bloquea todo lo demás (services/auth.py la deja exenta
explícitamente), igual que /legal.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from zascarr.config import get_settings
from zascarr.database import get_db
from zascarr.services.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE,
    crear_cookie_sesion,
    credenciales_validas,
    hash_password_async,
    necesita_rehash,
)
from zascarr.services.runtime_settings import RuntimeSettingsService
from zascarr.web.routes import crear_templates

templates = crear_templates()

router = APIRouter(tags=["auth"], include_in_schema=False)


def _next_seguro(destino: str) -> str:
    """`next` llega del query string, así que lo controla quien construye
    el enlace — nunca del propio servidor. Sin este filtro, un enlace tipo
    `/login?next=https://sitio-falso.example` redirigiría tras un login
    correcto a un dominio ajeno (open redirect clásico). Solo se acepta
    una ruta relativa de este mismo sitio."""
    # A6 (revisión 2026-09-26): el navegador, en una URL http(s), trata '\\'
    # como '/', de modo que `/\\host.invalid` se normaliza a `//host.invalid`
    # (protocol-relative) y apunta FUERA de este sitio. Ninguna ruta interna
    # legítima lleva backslash, así que se rechaza cualquier destino que lo
    # contenga — el caso '//' ya se cubría, el '/\\' no.
    if "\\" in destino:
        return "/"
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
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    next = _next_seguro(next)
    settings = get_settings()
    if not await credenciales_validas(username, password, settings):
        return templates.TemplateResponse(request, "login.html", {
            "next": next,
            "pide_usuario": settings.auth_mode == "user_password",
            "error": "Usuario o contraseña incorrectos.",
        }, status_code=401)

    # Rehasheo oportunista (p. ej. tras subir las iteraciones de PBKDF2): aquí es
    # donde hay contraseña en claro y ya validada. Se calcula en el ejecutor
    # propio (no bloquea el bucle de eventos) y NO toca `auth_session_version`:
    # subir iteraciones no debe cerrar las sesiones abiertas.
    if necesita_rehash(settings.auth_password_hash):
        nuevo_hash = await hash_password_async(password)
        await RuntimeSettingsService(db).save({"auth_password_hash": nuevo_hash})

    respuesta = RedirectResponse(next, status_code=303)
    respuesta.set_cookie(
        COOKIE_NAME,
        crear_cookie_sesion(settings.secret_key, settings.auth_session_version),
        max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
    )
    return respuesta


@router.post("/logout")
async def logout() -> RedirectResponse:
    respuesta = RedirectResponse("/login", status_code=303)
    respuesta.delete_cookie(COOKIE_NAME)
    return respuesta
