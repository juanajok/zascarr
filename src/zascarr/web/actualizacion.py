"""Ruta de UI para la actualización manual OPS4, deshabilitada por defecto.

El botón solo aparece si `OPS4_ACTUALIZACION_HABILITADA` es verdadero. La ruta
relee la clave dedicada, reautentica con la contraseña actual, emite el testigo
v4 y lo envía por el socket dedicado. No registra la contraseña, el testigo ni
la firma; `INCIERTA` no se presenta como éxito ni invita a reintentar.
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse

from zascarr.config import get_settings
from zascarr.services.clave_autorizacion import leer_clave_autorizacion
from zascarr.services.solicitud_actualizacion_v4 import (
    ResultadoSolicitudV4,
    solicitar_actualizacion_v4,
)

router = APIRouter(tags=["ui"])

_MENSAJES = {
    ResultadoSolicitudV4.NO_HABILITADA: "La actualización no está habilitada.",
    ResultadoSolicitudV4.CONFIRMACION_REQUERIDA: "Confirma que entiendes la operación.",
    ResultadoSolicitudV4.CONTRASENA_INVALIDA: "La contraseña no tiene un formato válido.",
    ResultadoSolicitudV4.AUTENTICACION_NO_ACTIVADA:
        "Activa la contraseña de la app antes de actualizar.",
    ResultadoSolicitudV4.CONTRASENA_INCORRECTA: "La contraseña actual no es correcta.",
    ResultadoSolicitudV4.OCUPADA: "Hay otra comprobación en curso; espera un momento.",
    ResultadoSolicitudV4.BLOQUEADA: "Demasiados intentos; espera antes de volver a probar.",
    ResultadoSolicitudV4.NO_DISPONIBLE: "El servicio de actualización no está disponible.",
    ResultadoSolicitudV4.ACEPTADA: "Solicitud aceptada. La actualización se está preparando.",
    ResultadoSolicitudV4.RECHAZADA: "La solicitud fue rechazada. No se ha actualizado nada.",
    ResultadoSolicitudV4.INCIERTA: (
        "No se pudo confirmar el resultado. No vuelvas a intentarlo: "
        "revisa el estado del host antes de actuar."
    ),
    ResultadoSolicitudV4.RESPUESTA_INVALIDA: "El host devolvió una respuesta no válida.",
}


@router.post("/ui/actualizar", response_class=HTMLResponse)
async def actualizar(
    request: Request,
    contrasena: str = Form(default=""),
    entiendo: str | None = Form(default=None),
) -> HTMLResponse:
    """Puerta deshabilitada por defecto; no hay botón activo en producción."""
    settings = get_settings()
    if not settings.ops4_actualizacion_habilitada:
        raise HTTPException(status_code=404, detail="No disponible")
    if entiendo != "si":
        return HTMLResponse("<p>Confirma que entiendes la operación.</p>", status_code=400)
    try:
        clave = await asyncio.to_thread(
            leer_clave_autorizacion,
            settings.ops4_autorizacion_key_file,
            uid_esperado=0,
            modo_esperado=0o440,
        )
    except ValueError:
        return HTMLResponse(
            "<p>La clave de actualización no está disponible.</p>", status_code=503,
        )
    resultado = await solicitar_actualizacion_v4(
        settings, clave=clave, contrasena=contrasena, entiendo=True,
        habilitada=True,
    )
    mensaje = _MENSAJES.get(
        resultado.resultado, "No se pudo completar la solicitud.",
    )
    return HTMLResponse(f"<p>{mensaje}</p>", status_code=200)
