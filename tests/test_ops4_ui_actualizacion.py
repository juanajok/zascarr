"""Puerta UI OPS4; sin host real, socket ni ejecución."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from zascarr.services.solicitud_actualizacion_v4 import (
    ResultadoSolicitudV4,
    SolicitudV4,
)
from zascarr.web import actualizacion


def config(**cambios):
    base = {
        "ops4_actualizacion_habilitada": False,
        "ops4_autorizacion_key_file": "/no/existe",
        "ops4_socket_file": "/no/existe.sock",
    }
    base.update(cambios)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_deshabilitada_da_404_sin_leer_clave_ni_servicio(monkeypatch) -> None:
    llamado = []
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config())
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: llamado.append(1))
    monkeypatch.setattr(
        actualizacion, "solicitar_actualizacion_v4",
        lambda *a, **k: llamado.append(2),
    )
    with pytest.raises(HTTPException) as error:
        await actualizacion.actualizar(None, "clave", "si")
    assert error.value.status_code == 404
    assert llamado == []


@pytest.mark.asyncio
async def test_confirmacion_obligatoria(monkeypatch) -> None:
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
    ))
    respuesta = await actualizacion.actualizar(None, "clave", None)
    assert respuesta.status_code == 400
    assert b"Confirma" in respuesta.body


@pytest.mark.asyncio
async def test_clave_ausente_da_503(monkeypatch) -> None:
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
    ))

    def falla(*_args, **_kwargs):
        raise ValueError("clave no disponible")

    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", falla)
    respuesta = await actualizacion.actualizar(None, "clave", "si")
    assert respuesta.status_code == 503
    assert b"clave" in respuesta.body


@pytest.mark.asyncio
async def test_servicio_aceptado_y_rechazado_sin_filtrar_secretos(monkeypatch) -> None:
    llamadas = []
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
    ))
    monkeypatch.setattr(
        actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32,
    )

    async def servicio(_settings, **kwargs):
        llamadas.append(kwargs)
        return SolicitudV4(ResultadoSolicitudV4.ACEPTADA, id="a" * 32)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", servicio)
    respuesta = await actualizacion.actualizar(None, "secreto", "si")
    assert respuesta.status_code == 200
    assert b"aceptada" in respuesta.body.lower()
    assert llamadas and llamadas[0]["contrasena"] == "secreto"
    assert llamadas[0]["habilitada"] is True
    assert b"secreto" not in respuesta.body

    async def rechazo(_settings, **_kwargs):
        return SolicitudV4(ResultadoSolicitudV4.CONTRASENA_INCORRECTA)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", rechazo)
    respuesta = await actualizacion.actualizar(None, "secreto", "si")
    assert respuesta.status_code == 200
    assert b"no es correcta" in respuesta.body


@pytest.mark.asyncio
async def test_incierta_no_invita_a_reintentar(monkeypatch) -> None:
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
    ))
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32)

    async def incierta(_settings, **_kwargs):
        return SolicitudV4(ResultadoSolicitudV4.INCIERTA)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", incierta)
    respuesta = await actualizacion.actualizar(None, "clave", "si")
    assert respuesta.status_code == 200
    assert b"No vuelvas a intentarlo" in respuesta.body
