"""Pruebas del preparador aislado; no existe transporte ni ejecución."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.ops import protocolo_actualizar_ops4 as protocolo
from zascarr.services.reautenticacion import Reauth, ResultadoReauth
from zascarr.services.solicitud_actualizacion import (
    ResultadoSolicitud,
    preparar_solicitud,
)

CLAVE = bytes(range(32))
ID = "a" * 32


def settings(tmp_path: Path, *, auth_mode: str = "password") -> SimpleNamespace:
    clave = tmp_path / "ops.key"
    # Igual que scripts/instalar_ops.sh: 64 hex + LF.
    clave.write_text(CLAVE.hex() + "\n", encoding="ascii")
    return SimpleNamespace(auth_mode=auth_mode, ops_key_file=str(clave))


async def comprobar_ok(_prueba: str, _settings: object) -> ResultadoReauth:
    return ResultadoReauth(Reauth.OK)


async def comprobar_incorrecta(_prueba: str, _settings: object) -> ResultadoReauth:
    return ResultadoReauth(Reauth.INCORRECTA)


@pytest.mark.asyncio
@pytest.mark.parametrize("entiendo", [False, 0, "sí", None])
async def test_confirmacion_obligatoria(tmp_path: Path, entiendo) -> None:
    llamadas = []

    async def comprobar(_p, _s):
        llamadas.append(1)
        return ResultadoReauth(Reauth.OK)

    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=entiendo, comprobar=comprobar
    )
    assert resultado.resultado is ResultadoSolicitud.CONFIRMACION_REQUERIDA
    assert llamadas == []


@pytest.mark.asyncio
@pytest.mark.parametrize("prueba", ["", "ñ" * 257, "\ud800", b"clave", None])
async def test_contrasena_invalida_no_reautentica(tmp_path: Path, prueba) -> None:
    llamadas = []

    async def comprobar(_p, _s):
        llamadas.append(1)
        return ResultadoReauth(Reauth.OK)

    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena=prueba, entiendo=True, comprobar=comprobar
    )
    assert resultado.resultado is ResultadoSolicitud.CONTRASENA_INVALIDA
    assert llamadas == []


@pytest.mark.asyncio
@pytest.mark.parametrize("modo,esperado", [
    ("none", ResultadoSolicitud.AUTENTICACION_NO_ACTIVADA),
    ("otro", ResultadoSolicitud.NO_DISPONIBLE),
])
async def test_modo_de_autenticacion_cerrado(tmp_path: Path, modo: str, esperado) -> None:
    llamadas = []

    async def comprobar(_p, _s):
        llamadas.append(1)
        return ResultadoReauth(Reauth.OK)

    resultado = await preparar_solicitud(
        settings(tmp_path, auth_mode=modo), contrasena="clave", entiendo=True,
        comprobar=comprobar,
    )
    assert resultado.resultado is esperado
    assert llamadas == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reauth,esperado", [
    (Reauth.INCORRECTA, ResultadoSolicitud.CONTRASENA_INCORRECTA),
    (Reauth.OCUPADA, ResultadoSolicitud.OCUPADA),
    (Reauth.BLOQUEADA, ResultadoSolicitud.BLOQUEADA),
])
async def test_resultados_de_reauth_no_preparan(tmp_path: Path, reauth, esperado) -> None:
    async def comprobar(_p, _s):
        return ResultadoReauth(reauth, 123.0 if reauth is Reauth.BLOQUEADA else None)

    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True, comprobar=comprobar
    )
    assert resultado.resultado is esperado
    assert resultado.linea is None
    if reauth is Reauth.BLOQUEADA:
        assert resultado.hasta_epoch == 123.0


@pytest.mark.asyncio
async def test_fallo_o_resultado_inesperado_de_reauth_falla_cerrado(tmp_path: Path) -> None:
    async def revienta(_p, _s):
        raise RuntimeError("secreto interno")

    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True, comprobar=revienta
    )
    assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE
    assert resultado.linea is None
    assert "secreto" not in repr(resultado)

    async def devuelve_nada(_p, _s):
        return None

    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True, comprobar=devuelve_nada
    )
    assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_ok_construye_peticion_verificable_sin_transporte(tmp_path: Path) -> None:
    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True,
        ahora=1800000000, id_=ID, comprobar=comprobar_ok,
    )
    assert resultado.resultado is ResultadoSolicitud.PREPARADA
    assert resultado.id == ID
    assert resultado.linea is not None
    datos = protocolo.parsear(resultado.linea.bytes())
    assert datos is not None
    assert datos["prueba"] == "clave"
    assert datos["creada"] == 1800000000
    assert protocolo.verificar_firma(CLAVE, datos)
    assert b"clave" not in resultado.linea.bytes().replace(b'"prueba":"clave"', b"")


@pytest.mark.asyncio
async def test_clave_ausente_o_invalida_falla_sin_filtrar(tmp_path: Path) -> None:
    s = settings(tmp_path)
    s.ops_key_file = str(tmp_path / "no-existe")
    resultado = await preparar_solicitud(
        s, contrasena="clave", entiendo=True, comprobar=comprobar_ok
    )
    assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE
    assert resultado.linea is None

    (tmp_path / "otra").write_text("no es una clave", encoding="ascii")
    s.ops_key_file = str(tmp_path / "otra")
    resultado = await preparar_solicitud(
        s, contrasena="clave", entiendo=True, comprobar=comprobar_ok
    )
    assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE
    assert "no es una clave" not in repr(resultado)


@pytest.mark.asyncio
async def test_linea_no_es_json_arbitrario(tmp_path: Path) -> None:
    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave", entiendo=True,
        ahora=0, id_=ID, comprobar=comprobar_ok,
    )
    assert resultado.linea is not None
    datos = json.loads(resultado.linea.bytes())
    assert set(datos) == {"v", "id", "accion", "creada", "prueba", "firma"}


@pytest.mark.asyncio
@pytest.mark.parametrize("longitud,esperado", [
    (512, ResultadoSolicitud.PREPARADA),
    (513, ResultadoSolicitud.CONTRASENA_INVALIDA),
])
async def test_limite_exacto_de_contrasena(tmp_path: Path, longitud: int, esperado) -> None:
    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="x" * longitud, entiendo=True,
        ahora=1800000000, id_=ID, comprobar=comprobar_ok,
    )
    assert resultado.resultado is esperado


@pytest.mark.asyncio
async def test_clave_por_enlace_o_fifo_se_rechaza_sin_bloquear(tmp_path: Path) -> None:
    real = tmp_path / "real.key"
    real.write_text(CLAVE.hex() + "\n", encoding="ascii")
    enlace = tmp_path / "enlace.key"
    enlace.symlink_to(real)
    s = settings(tmp_path)
    s.ops_key_file = str(enlace)
    resultado = await preparar_solicitud(
        s, contrasena="clave", entiendo=True, ahora=1800000000, id_=ID,
        comprobar=comprobar_ok,
    )
    assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE

    fifo = tmp_path / "fifo.key"
    os.mkfifo(fifo)
    s.ops_key_file = str(fifo)
    resultado = await asyncio.wait_for(preparar_solicitud(
        s, contrasena="clave", entiendo=True, ahora=1800000000, id_=ID,
        comprobar=comprobar_ok,
    ), timeout=2)
    assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE


@pytest.mark.asyncio
async def test_modo_user_password_y_parametros_invalidos(tmp_path: Path) -> None:
    resultado = await preparar_solicitud(
        settings(tmp_path, auth_mode="user_password"), contrasena="clave", entiendo=True,
        ahora=1800000000, id_=ID, comprobar=comprobar_ok,
    )
    assert resultado.resultado is ResultadoSolicitud.PREPARADA
    for campo, valor in (("id_", "no-hex"), ("ahora", True), ("ahora", -1)):
        kwargs = {"id_": ID, "ahora": 1800000000}
        kwargs[campo] = valor
        resultado = await preparar_solicitud(
            settings(tmp_path), contrasena="clave", entiendo=True,
            comprobar=comprobar_ok, **kwargs,
        )
        assert resultado.resultado is ResultadoSolicitud.NO_DISPONIBLE

@pytest.mark.asyncio
async def test_repr_y_asdict_no_exponen_la_peticion_ni_la_contrasena(tmp_path: Path) -> None:
    resultado = await preparar_solicitud(
        settings(tmp_path), contrasena="clave-secreta", entiendo=True,
        ahora=1800000000, id_=ID, comprobar=comprobar_ok,
    )
    assert "clave-secreta" not in repr(resultado)
    assert "clave-secreta" not in str(resultado)
    assert "clave-secreta" not in repr(asdict(resultado))
    assert "clave-secreta" not in repr(resultado.linea)
