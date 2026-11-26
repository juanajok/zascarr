"""Puerta UI OPS4; sin host real, socket ni ejecución."""
from __future__ import annotations

import time
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


@pytest.mark.asyncio
async def test_respuesta_invalida_advierte_que_pudo_empezar(monkeypatch) -> None:
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
    ))
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32)

    async def respuesta_invalida(_settings, **_kwargs):
        return SolicitudV4(ResultadoSolicitudV4.RESPUESTA_INVALIDA)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", respuesta_invalida)
    respuesta = await actualizacion.actualizar(None, "clave", "si")
    texto = respuesta.body.decode("utf-8")
    assert "podría haber empezado" in texto
    assert "No vuelvas a intentarlo" in texto
    assert "revisa el estado del host" in texto


@pytest.mark.asyncio
async def test_ruta_hasta_socket_real_con_consumo_durable(tmp_path, monkeypatch) -> None:
    import asyncio
    import json
    import os

    from deploy.ops.escritor_estado_actualizar_ops4 import escribir_estado
    from deploy.ops.registro_repeticiones_ops4 import (
        abrir_directorio_autorizaciones,
        crear_reclamador_durable,
    )
    from tests._host_v4 import CodigoV4, admitir_v4
    from zascarr.config import get_settings
    from zascarr.services.auth import hash_password
    from zascarr.services.clave_autorizacion import leer_clave_autorizacion
    from zascarr.services.reautenticacion import reiniciar_estado

    clave = bytes(range(32))
    key = tmp_path / "actualizar.key"
    key.write_text(clave.hex() + "\n", encoding="ascii")
    key.chmod(0o440)
    consumidos = tmp_path / "consumidos"
    consumidos.mkdir(mode=0o700)
    consumidos.chmod(0o700)
    fd = abrir_directorio_autorizaciones(consumidos, uid_esperado=os.getuid())
    ruta = tmp_path / "actualizar.sock"
    ruta_estado = tmp_path / "actualizar-status.json"
    settings = get_settings().model_copy(update={
        "ops4_estado_file": str(ruta_estado),
        "auth_mode": "password",
        "auth_username": "ana",
        "auth_password_hash": hash_password("secreta"),
        "ops4_actualizacion_habilitada": True,
        "ops4_autorizacion_key_file": str(key),
        "ops4_socket_file": str(ruta),
    })
    monkeypatch.setattr(actualizacion, "get_settings", lambda: settings)
    monkeypatch.setattr(
        actualizacion, "leer_clave_autorizacion",
        lambda path, **_kwargs: leer_clave_autorizacion(
            path, uid_esperado=os.getuid(), modo_esperado=0o440,
        ),
    )
    reclamar = crear_reclamador_durable(fd)

    async def handler(reader, writer):
        try:
            linea = await reader.readline()
            codigo = admitir_v4(
                linea, clave=clave, ahora=int(time.time()), reclamar_uso=reclamar,
            )
            resultado = "aceptada" if codigo is CodigoV4.ACEPTADA else "rechazada"
            ident = json.loads(linea)["id"]
            if codigo is CodigoV4.ACEPTADA:
                escribir_estado(ruta_estado, {
                    "schema": 1, "id": ident, "estado": "en_curso",
                    "inicio_epoch": int(time.time()),
                    "actualizado_epoch": int(time.time()),
                })
            writer.write((json.dumps(
                {"v": 4, "id": ident, "resultado": resultado,
                 "codigo": codigo.value}, separators=(",", ":"),
            ) + "\n").encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_unix_server(handler, path=str(ruta))
    reiniciar_estado()
    try:
        async with server:
            respuesta = await actualizacion.actualizar(None, "secreta", "si")
        assert respuesta.status_code == 200
        assert b"aceptada" in respuesta.body.lower()
        assert any(p.name.startswith("autorizacion-") for p in consumidos.iterdir())
    finally:
        reiniciar_estado()
        os.close(fd)


@pytest.mark.asyncio
async def test_respuesta_incoherente_por_socket_advierte_en_html(tmp_path, monkeypatch) -> None:
    import asyncio
    import json

    from starlette.requests import Request

    from zascarr.config import get_settings
    from zascarr.services.auth import hash_password
    from zascarr.services.reautenticacion import reiniciar_estado

    ruta = tmp_path / "actualizar.sock"
    settings = get_settings().model_copy(update={
        "auth_mode": "password", "auth_username": "ana",
        "auth_password_hash": hash_password("secreta"),
        "ops4_actualizacion_habilitada": True,
        "ops4_socket_file": str(ruta),
    })
    monkeypatch.setattr(actualizacion, "get_settings", lambda: settings)
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32)
    recibidas = []

    async def handler(reader, writer):
        try:
            solicitud = json.loads(await reader.readline())
            recibidas.append(solicitud["id"])
            writer.write((json.dumps({
                "v": 4, "id": solicitud["id"],
                "resultado": "rechazada", "codigo": "incierta",
            }) + "\n").encode())
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    request = Request({
        "type": "http", "http_version": "1.1", "method": "POST",
        "path": "/ui/actualizar", "raw_path": b"/ui/actualizar",
        "query_string": b"", "headers": [], "client": ("test", 1),
        "server": ("test", 80), "scheme": "http", "root_path": "",
    })
    server = await asyncio.start_unix_server(handler, path=str(ruta))
    reiniciar_estado()
    try:
        async with server:
            respuesta = await actualizacion.actualizar(request, "secreta", "si")
        texto = respuesta.body.decode("utf-8")
        assert len(recibidas) == 1
        assert respuesta.status_code == 200
        assert "<html" in texto
        assert "podría haber empezado" in texto
        assert "No vuelvas a intentarlo" in texto
        assert "revisa el estado del host" in texto
        assert "Solicitud aceptada" not in texto
    finally:
        reiniciar_estado()


@pytest.mark.asyncio
async def test_resultado_se_pinta_en_el_layout_normal(monkeypatch) -> None:
    from starlette.requests import Request

    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
    ))
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32)

    async def aceptada(_settings, **_kwargs):
        return SolicitudV4(ResultadoSolicitudV4.ACEPTADA, id="a" * 32)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", aceptada)
    request = Request({
        "type": "http", "http_version": "1.1", "method": "POST",
        "path": "/ui/actualizar", "raw_path": b"/ui/actualizar",
        "query_string": b"", "headers": [], "client": ("test", 1),
        "server": ("test", 80), "scheme": "http", "root_path": "",
    })
    respuesta = await actualizacion.actualizar(request, "clave", "si")
    assert respuesta.status_code == 200
    assert b"<html" in respuesta.body
    assert b"Volver a Estado" in respuesta.body
    assert b"Solicitud aceptada" in respuesta.body


@pytest.mark.asyncio
async def test_estado_fallido_no_se_pinta_como_exito(monkeypatch, tmp_path) -> None:
    from starlette.requests import Request

    from deploy.ops.escritor_estado_actualizar_ops4 import escribir_estado

    ruta = tmp_path / "actualizar-status.json"
    escribir_estado(ruta, {
        "schema": 1, "id": "a" * 32, "estado": "fallida",
        "inicio_epoch": int(time.time()) - 5,
        "actualizado_epoch": int(time.time()) - 1,
    })
    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
        ops4_estado_file=str(ruta),
    ))
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32)

    async def aceptada(_settings, **_kwargs):
        return SolicitudV4(ResultadoSolicitudV4.ACEPTADA, id="a" * 32)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", aceptada)
    request = Request({
        "type": "http", "http_version": "1.1", "method": "POST",
        "path": "/ui/actualizar", "raw_path": b"/ui/actualizar",
        "query_string": b"", "headers": [], "client": ("test", 1),
        "server": ("test", 80), "scheme": "http", "root_path": "",
    })
    respuesta = await actualizacion.actualizar(request, "clave", "si")
    assert respuesta.status_code == 200
    assert b"no termin\xc3\xb3 bien" in respuesta.body
    assert b'href="/estado"' in respuesta.body


@pytest.mark.asyncio
async def test_ocupada_no_se_convierte_en_incierta_por_leer_estado(monkeypatch, tmp_path) -> None:
    from starlette.requests import Request

    monkeypatch.setattr(actualizacion, "get_settings", lambda: config(
        ops4_actualizacion_habilitada=True,
        ops4_estado_file=str(tmp_path / "no-existe.json"),
    ))
    monkeypatch.setattr(actualizacion, "leer_clave_autorizacion", lambda *a, **k: b"k" * 32)

    async def ocupada(_settings, **_kwargs):
        return SolicitudV4(ResultadoSolicitudV4.OCUPADA, id="a" * 32)

    monkeypatch.setattr(actualizacion, "solicitar_actualizacion_v4", ocupada)
    request = Request({
        "type": "http", "http_version": "1.1", "method": "POST",
        "path": "/ui/actualizar", "raw_path": b"/ui/actualizar",
        "query_string": b"", "headers": [], "client": ("test", 1),
        "server": ("test", 80), "scheme": "http", "root_path": "",
    })
    respuesta = await actualizacion.actualizar(request, "clave", "si")
    assert respuesta.status_code == 200
    assert b"otra comprobaci\xc3\xb3n en curso" in respuesta.body
    assert b"No vuelvas a intentarlo" not in respuesta.body
